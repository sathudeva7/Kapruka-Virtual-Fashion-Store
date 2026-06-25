# Kapruka Shopping Assistant — A Plain-English Guide

This guide explains what this software is and how its pieces fit together, written for someone who does not write code. No technical background needed. Where a technical word is unavoidable, it is explained in plain words right after it.

---

## What is this app?

Imagine walking into a friendly clothing boutique in Sri Lanka. A warm, knowledgeable shop assistant greets you, asks what you are looking for, pulls clothes off the rack, suggests a whole outfit for the wedding you are attending, lets you "see" how something would look on you using your photo, and then helps you pay and arrange delivery.

This app is that boutique — but online, and the shop assistant is an **AI** (artificial intelligence — a computer program that understands and replies in natural language, like a chatbot).

A few key facts in plain terms:

- It sells **fashion only** — clothing (sarees, dresses, shirts, blouses, kids' wear) and fashion accessories (shoes, handbags, belts, eyewear). It politely declines requests for food, cakes, flowers, electronics, jewellery, perfume, or gifts, even though the wider Kapruka website sells those.
- The actual products, prices, and stock come **live from Kapruka.com** (Sri Lanka's largest online store). The app does not keep its own product list — it asks Kapruka's system in real time, like a shop assistant phoning the warehouse to check what's on the shelves today.
- You can chat by **typing**, or in some modes by **talking** (voice), in English, Sinhala, Tamil, or romanized mixes like "Singlish" and "Tanglish." The assistant replies in whatever language and style you used.
- There is a standout feature: a **virtual try-on**, where you upload a photo of yourself and the app generates a picture of *you* wearing a chosen garment.
- When you are ready to buy, it collects your delivery details, checks delivery is possible, and gives you a real **pay-now link**.

Behind the scenes, the "shop assistant" is not one single program. It is a **team of specialists**, each with one job — much like a real store has a sales floor person, a stylist, a fitting-room attendant, and a checkout cashier.

---

## Who are the helpers (the agents) and what does each one do?

In this app, each helper is called an **agent** (an AI helper with one specific job and its own set of allowed actions). Think of them as staff members in the boutique. A customer only ever talks to one of them at a time, and a "manager" decides who should handle each request.

### The Greeter / Manager (the "root" agent)

This is the host at the door. Their *only* job is to listen to what you want and hand you off to the right specialist — they do not answer product questions themselves.

- "I want a red shirt" → sent to the **Product Finder**.
- "What should I wear to a wedding?" → sent to the **Stylist**.
- "Try this on me" → sent to the **Fitting Room attendant**.
- "I'd like to buy and pay" → sent to the **Checkout cashier**.

Like a good host, they greet you warmly, maybe ask one quick clarifying question, then pass you along. They deliberately keep a very plain personality — for a quirky technical reason explained later, giving the host a big chatty personality caused problems, so the warmth lives with the specialists instead.

### The Product Finder (the "catalog" agent)

This is the experienced sales-floor assistant. You tell them what you need and they search Kapruka's shelves, then recommend a small number of good options — usually no more than three — each with a one-line reason it suits *you* (the colour, the fabric, what it pairs with, whether it fits the occasion).

- They lead with their top pick instead of dumping a long list.
- They tip into local know-how: weddings, office wear, Avurudu, Christmas, Deepavali, and the warm climate (favouring breathable fabrics for daytime events).
- They manage your **shopping cart** (your basket of items to buy): adding, removing, changing quantities.
- If a search comes back empty, they try broader search words rather than giving up.

### The Stylist (the "stylist" agent)

This is the personal stylist who composes a *whole coordinated look*, not just one item. Ask "style me for a party" and they will assemble an outfit across up to four "slots":

1. a main garment,
2. footwear,
3. a bag,
4. an accessory.

If you give a budget, they split it sensibly across those slots (roughly: most on the main garment, less on shoes and bag, a little on the accessory). They search for one item per slot, then present the finished look as one outfit and explain why the pieces work together.

Two thoughtful touches:

- They have a built-in limit on how many times they will search in one go, so they don't get stuck endlessly hunting.
- They **remember** what they suggested before, so if you say "style me again," you get a *fresh* outfit rather than the same pieces.

### The Fitting Room attendant (the "fittingroom" agent)

This is the helper who runs the magic mirror — the virtual try-on. When you ask to try something on, they take the photo you uploaded and the garment's picture and produce an image of you wearing it. (How that works is its own section below.)

They also handle the "what if it goes wrong" moments gracefully — for example, if you haven't uploaded a photo yet, they kindly ask you to tap the camera button first.

### The Checkout cashier (the "checkout" agent)

This is the person at the till. Once you're ready to buy, they:

- check your basket isn't empty,
- make sure they have your name, phone, delivery address, city, and delivery date,
- confirm Kapruka can actually deliver to that place on that date, and tell you the delivery fee,
- offer to add a gift message if it looks like a gift,
- show you a clear order summary and **wait for you to confirm**,
- and only then place the real order and hand you a pay-now link.

There's also a small **delivery-checker helper** (the "logistics" agent) whose sole job is to confirm whether Kapruka delivers to a given city on a given date, and at what rate.

A nice safety habit: the cashier never tries to *hear and type* your name, phone, or address (easy to mishear). Instead it asks you to type those into an on-screen form, and it builds the order from those saved details — not from anything it guessed.

---

## How a typical shopping conversation flows, step by step

Here's what happens when you shop, told as a story:

1. **You say hello / ask for something.** "Hi, I need an outfit for a wedding next month."

2. **The Greeter routes you.** It recognises this is an "outfit" request and hands you to the **Stylist** (a single product request would have gone to the Product Finder instead).

3. **The specialist works your request.** The Stylist figures out the occasion and budget, then searches Kapruka for each piece of the outfit. The Product Finder, by contrast, would search for the one thing you asked about.

4. **Real product cards appear.** As the assistant searches, the app quietly captures the actual products — name, price, photo, whether they're in stock, a link — and shows them to you as neat **product cards** (little tiles with a picture and price). The assistant's chatty reply explains *why* these picks suit you; the cards show the *what*. (This split is deliberate — see the next paragraph.)

5. **You react.** You might say "add the blue saree to my cart," "show me cheaper shoes," or tap a card's **Try on** button.

6. **You move toward buying.** When you say you're ready, the Greeter passes you to the **Checkout cashier**, who collects/confirms your details, checks delivery, and gives you the pay link.

**Why cards *and* chat?** The AI naturally talks in sentences, which would lose the product photos and exact prices. So the app catches the real product details behind the scenes and renders them as picture cards, while the assistant keeps talking like a human. You get both the warmth of a conversation and the clarity of a proper product listing.

Throughout, replies stream in **live**, word by word, so you're not staring at a blank screen waiting — much like watching someone type a message to you in real time.

---

## The cool trick: trying clothes on your own photo

This is the feature people remember. Here's the plain version:

1. You tap the **camera button** and upload a clear, front-facing photo of yourself. (Allowed types are common photo formats, up to a sensible size limit. Your raw photo is kept only in the app's temporary memory for your session — it is not saved into the public website files.)

2. You pick a garment and tap **Try on** (on the chat path you can also just say "try on product 123").

3. The app fetches that garment's picture, hands both images — your photo plus the garment — to an **image-generating AI** (a model that creates new pictures), and asks it to dress *you* in that garment.

4. A few seconds later (usually 10–30), a brand-new image appears in the chat showing you wearing the item. You can even try on a **whole outfit at once** — several items combined into one coordinated picture.

The instructions given to the image AI are unusually strict about one thing: **keeping you looking like you.** It is told, in no uncertain terms, to preserve your exact face, skin, hair, body shape, age, and so on — only the clothes should change. There's even a memorable check baked in: *would your own mother instantly recognise you in the result?* If not, it's considered wrong.

If something can't work — no photo uploaded, the garment image won't download, or the AI declines the photo — the Fitting Room attendant tells you plainly and never pretends an image was made.

(Under the hood the app can use one of two different image AIs, but you don't need to think about that — the experience is the same.)

---

## How buying actually happens

When you decide to buy, the process is careful and honest by design:

1. **Your basket is checked.** If it's empty, the cashier says so and stops.

2. **Your details are gathered safely.** Name, phone, delivery address, city, and date. As mentioned, you type these into a form rather than dictating them, so nothing gets misheard.

3. **Delivery is verified.** The app asks Kapruka whether it can deliver to your city on your chosen date, and reports the delivery fee and any warnings.

4. **You see a clear review and confirm.** Items, quantities, address, date, fee. Nothing is bought until you say yes.

5. **The real order is placed — carefully.** Here's an important safeguard: the actual order is *not* assembled from anything the AI might have typed. It is built strictly from the saved facts — your real basket, your saved name and address. This means a mistake by the AI (a wrong price or product) cannot reach the real order. The AI's only freedom is small extras like an optional gift message.

6. **You get a pay-now link.** This is a real, time-limited link (it expires after a while) that takes you to payment. The app also guards against accidentally placing the **same order twice** — if you confirm again with the identical basket and delivery, it simply hands back the existing link instead of creating a duplicate.

In short: real products, real delivery checks, a real payment link — with several quiet safety nets so nothing surprising or duplicated happens.

---

## Words you might hear, explained simply

- **Agent** — an AI helper with one job. This app has a team of them (greeter, product finder, stylist, fitting-room attendant, checkout cashier).

- **AI / model** — a computer program that understands language (or generates images) and responds like a person would. The chat uses a language model; the try-on uses an image-generating model.

- **Cart / basket** — your running list of items to buy, just like a shopping trolley.

- **Catalog** — the collection of products available to buy. Here the catalog lives on Kapruka.com, and the app reads from it live.

- **Checkout** — the buying-and-paying step at the end.

- **Product card** — a small on-screen tile showing one product's picture, name, price, and stock, sometimes with a "Try on" button.

- **Session** — your single visit/conversation. Your uploaded photo and basket belong to your session and aren't shared with other shoppers.

- **Streaming** — replies appearing live, a bit at a time, instead of all at once after a pause.

- **Try-on (virtual try-on)** — generating a picture of *you* wearing a chosen item, from your uploaded photo.

- **Voice mode** — talking to the assistant out loud instead of typing; it talks back. Some languages use one technology for this and others (like Sinhala) use a different one, but to you it just feels like a spoken conversation.

- **Delivery check** — confirming Kapruka can deliver to your city on your date, and the fee for it.

- **Pay link / checkout link** — the real, time-limited web link that takes you to payment after you confirm your order.

---

### A note on personality and language

The assistant is written to feel like a *warm, switched-on Sri Lankan friend who knows the whole shop* — proactive, not robotic. It tries to read the occasion and the feeling behind your request, suggest a thoughtful angle, ask at most one question, and always end with a clear next step. And it mirrors your language and style: write in Sinhala and it replies in Sinhala; mix English and romanized Sinhala ("mata wedding ekakata andinna ona") and it happily mixes right back.

*One small behind-the-scenes quirk worth knowing:* the AI's safety filter can get oversensitive if both a long personality description and long instructions are loaded onto the same helper at once — it would sometimes refuse to answer for no real reason. So the team deliberately gives the full warm personality only to the helpers that most need it (the Product Finder and the Checkout cashier) and keeps the others lean. It's a small trade-off that keeps the whole experience reliable.
