"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { imgUrl } from "./api";

// Load a remote image (through the backend /img proxy) as a WebGL texture,
// imperatively, so a missing image degrades to null instead of throwing/
// suspending. Shared by product frames, lookbook posters and mannequins.
export function useImgTexture(remote?: string | null): THREE.Texture | null {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const url = imgUrl(remote);
    if (!url) return;
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    loader.load(
      url,
      (t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        if (mounted.current) setTex(t);
      },
      undefined,
      () => {} // leave null on error
    );
    return () => {
      mounted.current = false;
    };
  }, [remote]);

  return tex;
}
