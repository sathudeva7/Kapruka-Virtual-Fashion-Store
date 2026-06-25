"""The virtual try-on tool: user photo + garment image → Gemini-generated
image of the user wearing the garment.

This module must stay importable without FastAPI (adk web imports the agent
graph too). Uploaded photos live in `tools.photostore.photo_store` (in-memory by
default, S3 in prod) — the /upload_photo endpoint writes to it, this module
reads from it. Drains tools.sinks.image_sink into `tryon_image` SSE frames.
"""

import asyncio
import base64
import hashlib
import os
import struct
import uuid
from pathlib import Path

import httpx
from google import genai
from google.genai import types
from google.adk.tools import ToolContext

from tools.sinks import image_sink, current_session_id
from tools.photostore import photo_store

TRYON_MODEL = os.getenv("TRYON_MODEL", "gemini-3-pro-image")

# Which image backend renders the try-on: "gemini" (default) or "grok".
# Grok (xAI) does identity-preserving image editing too, but it caps a request at
# 3 source images and we only wire SINGLE-item try-on for it (1 garment + the
# user photo). Set TRYON_PROVIDER=grok + XAI_API_KEY in .env to A/B test it.
TRYON_PROVIDER = os.getenv("TRYON_PROVIDER", "gemini").lower()
XAI_API_KEY = os.getenv("XAI_API_KEY")
GROK_TRYON_MODEL = os.getenv("GROK_TRYON_MODEL", "grok-imagine-image-quality")

# Generated images ARE served: /static/generated/<uuid>.png
GENERATED_DIR = Path(__file__).resolve().parent.parent / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# Try-on prompt — mirrors the fashion-app-demo's doFitting(): the tool
# instructions come first, then each product image with a label, then a short
# preservation note, then the user's photo LAST ("the reference image at the end
# gets the most attention from the model"). See contents=[...] in try_on().
TRYON_PROMPT = """\
Virtual Try-On Image Generation — Identity-Preserving

You are generating an image of a SPECIFIC PERSON wearing new clothing. The
reference person's identity is sacred. Do not invent a new person.

What you receive
- PRODUCT IMAGES (labelled "Product image N") come FIRST, above: clothing items
  or accessories to put ONTO the reference person. Each product image shows only
  the garment; if it is on another model, mannequin or hanger, take ONLY the
  garment, never that other person or background.
- The REFERENCE PERSON photo is the LAST image (shown below the products). Treat
  it as a fixed identity anchor — the single source of truth for who the person
  is. The hard identity rules accompanying that last image override everything.

What you CAN change
- Clothing — replace the person's existing garments with the products above. Do
  not keep or blend their original outfit.
- Background — optionally adjust to a setting that fits the new outfit.
- Pose — minor adjustments only, to make the outfit look natural; do not change
  the framing dramatically.

How to apply the products
- Full-body garments (dresses, jumpsuits): replace both upper and lower body
  clothing.
- Tops (shirts, jackets): replace only the upper body.
- Bottoms (pants, skirts, shorts): replace only the lower body.
- Accessories (hats, sunglasses, bags, shoes): add at the appropriate location
  without disturbing the body or face.
- Apply ALL provided products together in one cohesive outfit.

Output quality
- Photorealistic. It should look like an actual photograph of THE SAME PERSON as
  the reference photo, just in different clothes.
- Resolution at least as high as the reference photo.
- Natural lighting consistent with the chosen background.
"""

# Sent right before the user photo (the last part) — the identity anchor. This
# sits next to the reference image, which gets the most attention from the model.
PRESERVATION_TEXT = """\
This LAST image is the REFERENCE PERSON. You MUST preserve all of the following
from it, exactly. Do not invent a new person.

- Face geometry — eye shape, eye color, eye spacing, eyebrow shape and thickness,
  nose shape and width, mouth shape, lip fullness, chin shape, jawline, cheekbone
  structure, forehead shape.
- Skin — skin tone, undertone, freckles, moles, scars, birthmarks, age lines, and
  any other identifying skin feature. Do NOT smooth, lighten, or "improve" the skin.
- Hair — exact color (including roots, highlights, gray strands), length, parting,
  texture, curl pattern, hairline.
- Body shape — height proportion, shoulder width, torso shape, arm thickness, leg
  shape, posture. Do NOT slim, muscle-up, or otherwise alter the body.
- Ethnicity, age, and gender presentation — exactly as in this image. Do NOT shift
  any of these.

If any of these would change in your output, your output is wrong — start over.
Apply ONLY the product garment(s) shown above onto this exact person.

Self-check before returning: "If I showed this image and the reference photo to
the person's mother, would she immediately recognise both as her child?" If not,
the face fidelity is wrong — fix it before emitting the image."""

# Grok takes its source images as an `images` array and the prompt refers to them
# positionally as <IMAGE_0>, <IMAGE_1>, … We pass [garment, person] in that order.
GROK_TRYON_PROMPT = """\
Virtual try-on, identity-preserving. There are two reference images.
<IMAGE_0> is a CLOTHING PRODUCT — take ONLY the garment from it, ignoring any model,
mannequin, hanger or background it is shown on.
<IMAGE_1> is the REFERENCE PERSON and the single source of truth for who the person
is. Generate one photorealistic image of THIS EXACT person from <IMAGE_1> now wearing
the garment from <IMAGE_0>.

Preserve from <IMAGE_1>, exactly: face geometry and every feature, skin tone and all
marks (freckles, moles, scars), hair colour/length/texture/hairline, body shape and
proportions, ethnicity, age and gender presentation. Do NOT beautify, slim, lighten
or otherwise alter the person — change ONLY the clothing. Replace their original
outfit appropriately: full-body garments (dresses, jumpsuits) replace both upper and
lower body; tops replace only the upper body; bottoms only the lower body. The result
must be the same person their own mother would instantly recognise. Output a single
photorealistic image at least as high-resolution as <IMAGE_1>."""


def stable_seed(s: str) -> int:
    """Deterministic 31-bit seed from a string (sha256 of the first 4 bytes).

    Seeding the image model on the user's photo keeps the generated face
    consistent across re-runs for the same person, instead of drifting each
    time. Adapted from the fashion-app-demo's stableSeed().
    """
    digest = hashlib.sha256(s.encode()).digest()
    return struct.unpack(">I", digest[:4])[0] & 0x7FFFFFFF


def _img_ext(data: bytes) -> str:
    """Pick a file extension from the image's magic bytes (Grok may return JPEG
    or WebP, not just PNG) so StaticFiles serves the right content-type."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"

_client: genai.Client | None = None


def _genai_client() -> genai.Client:
    # Lazy so importing the agent graph never requires the API key.
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def _download_garment(url: str) -> tuple[bytes | None, str, str]:
    """Fetch the product image. Returns (bytes, mime, error) — bytes is None on
    failure. Browser-ish User-Agent: the CDN may reject bare clients."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
            resp = await http.get(
                url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36"}
            )
    except Exception as exc:
        return None, "", f"download failed: {exc}"
    if resp.status_code != 200 or not resp.content:
        return None, "", f"download failed: HTTP {resp.status_code}"
    mime = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
    return resp.content, mime, ""


async def _render_gemini(
    session_id: str | None,
    user_bytes: bytes,
    user_mime: str,
    garments_blobs: list[tuple[bytes, str]],
) -> tuple[bytes | None, str]:
    """Gemini image-edit backend. Returns (image_bytes, error_message).

    Prompt order mirrors the reference doFitting(): tool instructions → each
    product image (labelled) → preservation note → user photo LAST (the model
    weights the final reference image most heavily).
    """
    contents: list = [TRYON_PROMPT]
    for n, (gbytes, gmime) in enumerate(garments_blobs, start=1):
        contents.append(f"Product image {n} to apply to the person below:")
        contents.append(types.Part.from_bytes(data=gbytes, mime_type=gmime))
    contents.append(PRESERVATION_TEXT)
    contents.append(types.Part.from_bytes(data=user_bytes, mime_type=user_mime))

    try:
        result = await _genai_client().aio.models.generate_content(
            model=TRYON_MODEL,
            contents=contents,
            # Image-only output, very low temperature, deterministic per-photo seed.
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                temperature=0.05,
                seed=stable_seed(session_id or "kapruka"),
            ),
        )
    except Exception as exc:
        msg = str(exc)
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            return None, ("The fitting room is busy right now (image quota hit) "
                          "— please try again in a minute or two.")
        return None, f"Image generation failed: {msg[:200]}"

    candidates = result.candidates or []
    parts = (candidates[0].content.parts if candidates and candidates[0].content else None) or []
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline is not None and inline.data:
            return inline.data, ""
    return None, ("The model returned no image — it may have declined this photo. "
                  "Try a clearer, front-facing photo.")


async def _render_grok(
    user_bytes: bytes,
    user_mime: str,
    garment_blob: tuple[bytes, str],
) -> tuple[bytes | None, str]:
    """Grok (xAI) image-edit backend — single garment only. Returns
    (image_bytes, error_message). Posts the garment + user photo as base64 data
    URIs to /v1/images/edits; the prompt refers to them as <IMAGE_0>/<IMAGE_1>."""
    if not XAI_API_KEY:
        return None, "Grok try-on is not configured (XAI_API_KEY missing in .env)."
    gbytes, gmime = garment_blob
    garment_uri = f"data:{gmime};base64," + base64.b64encode(gbytes).decode()
    person_uri = f"data:{user_mime};base64," + base64.b64encode(user_bytes).decode()
    body = {
        "model": GROK_TRYON_MODEL,
        "prompt": GROK_TRYON_PROMPT,
        "images": [
            {"url": garment_uri, "type": "image_url"},  # <IMAGE_0> = garment
            {"url": person_uri, "type": "image_url"},   # <IMAGE_1> = the person
        ],
        "response_format": "b64_json",
        "n": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as http:
            resp = await http.post(
                "https://api.x.ai/v1/images/edits",
                headers={"Authorization": f"Bearer {XAI_API_KEY}",
                         "Content-Type": "application/json"},
                json=body,
            )
    except Exception as exc:
        return None, f"Image generation failed: {exc}"
    if resp.status_code == 429:
        return None, ("The fitting room is busy right now (image quota hit) "
                      "— please try again in a minute or two.")
    if resp.status_code != 200:
        return None, f"Image generation failed: HTTP {resp.status_code} {resp.text[:200]}"

    try:
        data = resp.json().get("data") or []
        b64 = data[0].get("b64_json") if data else None
    except Exception:
        b64 = None
    if not b64:
        return None, "Grok returned no image — try a clearer, front-facing photo."
    try:
        return base64.b64decode(b64), ""
    except Exception:
        return None, "Grok returned a malformed image."


async def generate_tryon(session_id: str | None, garments: list[dict]) -> dict:
    """Core try-on image generation — no LLM, no ToolContext, no contextvars.

    `garments` is a list of `{"id","name","image_url"}`. Reads the uploaded photo
    from `photo_store` (keyed by session_id), downloads each garment image, asks
    the image model to dress the person, saves the PNG under /static/generated,
    and returns a status dict with `image_url` on success. Shared by both the
    direct /try_on HTTP endpoint and the `try_on` agent tool below.
    """
    resolved = [g for g in (garments or []) if g.get("image_url")]
    if not resolved:
        return {"status": "unknown_product",
                "message": "No product image available to try on."}

    # Off-thread: the S3 backend does a blocking network GET (memory is instant).
    photo = await asyncio.to_thread(photo_store.get, session_id) if session_id else None
    if photo is None:
        return {
            "status": "no_photo",
            "message": "No photo uploaded for this session. Upload a clear, "
                       "front-facing photo first, then try again.",
        }

    # Download every garment image; drop any that fail but keep going. Keep each
    # garment paired with its product dict so ids/names stay correct even when a
    # download fails or an extra item gets skipped.
    downloaded: list[tuple[dict, bytes, str]] = []
    failed: list[str] = []
    for item in resolved:
        gbytes, gmime, _err = await _download_garment(item["image_url"])
        if gbytes is None:
            failed.append(str(item.get("id")))
        else:
            downloaded.append((item, gbytes, gmime))
    if not downloaded:
        return {"status": "garment_image_failed",
                "message": "Could not fetch the product image(s) for " +
                           ", ".join(failed) + "."}

    user_bytes, user_mime = photo

    # Pick the image backend. Grok currently does SINGLE-item try-on only, so it
    # dresses the person in the first garment and skips any extras; Gemini renders
    # all of them together as one coordinated look.
    if TRYON_PROVIDER == "grok":
        used = downloaded[:1]
        _item, gbytes, gmime = used[0]
        image_bytes, gen_err = await _render_grok(user_bytes, user_mime, (gbytes, gmime))
    else:
        used = downloaded
        garments_blobs = [(b, m) for (_i, b, m) in used]
        image_bytes, gen_err = await _render_gemini(
            session_id, user_bytes, user_mime, garments_blobs
        )
    if image_bytes is None:
        return {"status": "generation_failed", "message": gen_err}

    # Anything beyond what `used` covers (e.g. extra items Grok can't take) is
    # reported back honestly.
    for item, _b, _m in downloaded[len(used):]:
        sid = str(item.get("id"))
        if sid not in failed:
            failed.append(sid)

    used_items = [item for (item, _b, _m) in used]
    names = [item["name"] for item in used_items if item.get("name")]
    combined_name = " + ".join(names) if names else None

    filename = f"{uuid.uuid4().hex}.{_img_ext(image_bytes)}"
    (GENERATED_DIR / filename).write_bytes(image_bytes)
    payload = {
        "status": "ok",
        "image_url": f"/static/generated/{filename}",
        "product_id": ",".join(str(item["id"]) for item in used_items),
        "product_name": combined_name,
    }
    if failed:
        payload["skipped_product_ids"] = failed
    return payload


async def try_on(tool_context: ToolContext, product_ids: list[str]) -> dict:
    """Render the user's uploaded photo wearing one or more products.

    Pass a single id in a list (`["123"]`) to try on one garment, or several
    ids (`["123","456","789"]`) to render a whole coordinated outfit in one
    image. Needs a photo uploaded via the camera button first, and every product
    must have been seen in this session (searched or fetched) so its image is
    known. On status "ok" the generated image is ALREADY shown to the user in the
    chat — just add a short styling comment. On any other status, relay the
    message and never claim an image was generated.
    """
    # Tolerate the model passing a bare string instead of a list.
    if isinstance(product_ids, str):
        product_ids = [product_ids]
    ids = [str(pid) for pid in (product_ids or []) if str(pid).strip()]
    if not ids:
        return {"status": "unknown_product",
                "message": "No product ids given. Provide at least one product id to "
                           "try on."}

    seen = tool_context.state.get("seen_products") or {}
    garments: list[dict] = []
    missing: list[str] = []
    for pid in ids:
        info = seen.get(pid)
        if info and info.get("image_url"):
            garments.append({"id": pid, "name": info.get("name"), "image_url": info["image_url"]})
        else:
            missing.append(pid)
    if missing:
        # Have the agent fetch the missing ones, then call try_on again.
        return {
            "status": "unknown_product",
            "missing_product_ids": missing,
            "message": "No image known for product(s) " + ", ".join(missing) +
                       ". Look each up with kapruka_get_product first, then call "
                       "try_on again with all the product ids.",
        }

    result = await generate_tryon(current_session_id.get(), garments)

    if result.get("status") == "ok":
        # Surface the image into the chat/voice stream (the direct /try_on
        # endpoint returns the URL in its response instead, so it skips this).
        sink = image_sink.get()
        if sink is not None:
            sink.append({
                "url": result["image_url"],
                "product_id": result.get("product_id"),
                "product_name": result.get("product_name"),
            })
        note = "The image is already displayed to the user in the chat."
        if result.get("skipped_product_ids"):
            note += (" Note: could not fetch images for " +
                     ", ".join(result["skipped_product_ids"]) + ", so those were left out.")
        return {
            "status": "ok",
            "image_url": result["image_url"],
            "product_name": result.get("product_name"),
            "note": note,
        }
    return result
