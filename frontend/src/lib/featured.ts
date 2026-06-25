// Curated default products so the boutique walls are full the moment it loads —
// instead of showing the "Ask the assistant…" placeholder. These are real,
// in-stock Kapruka items (gathered via the Kapruka MCP search); image_url is the
// raw CDN URL (textured through the /img proxy by useImgTexture). seedFeatured()
// in store.ts drops these onto a section's rack only while it's still empty, so a
// real search/voice result replaces them cleanly (see addProduct + freshBatch).

import type { ProductItem, Section } from "./store";

export const FEATURED: Record<Section, ProductItem[]> = {
  women: [
    {
      id: "EF_PC_CLOT0V170POD00072",
      name: "Womens Boho Maxi Long Dress",
      price: 6490,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc00100/clot0v170p00072/clot0v170p00072_1.jpg",
      url: "https://www.kapruka.com/buyonline/womens-boho-maxi-long-dress/kid/ef_pc_clot0v170pod00072",
    },
    {
      id: "EF_PC_CLOT0V3099POD00005P",
      name: "Hand Embroidered Womens Kurti Dress Top",
      price: 21950,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc01347/clot0v3099p00005/clot0v3099p00005_1.jpg",
      url: "https://www.kapruka.com/buyonline/hand-embroidered-womens-kurti-/kid/ef_pc_clot0v3099pod00005p",
    },
    {
      id: "CLOTHING07923",
      name: "Traditional Kerala Kasavu Saree",
      price: 3750,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/shops/specialGifts/productImages/1736327490166_dsc2934copy.jpg",
      url: "https://www.kapruka.com/buyonline/traditional-kerala-kasavu-saree/kid/clothing07923",
    },
    {
      id: "EF_PC_CLOT0V154POD00857",
      name: "Pixcel Crush Silk Saree",
      price: 13690,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc00080/clot0v154p00857/clot0v154p00857_1.jpg",
      url: "https://www.kapruka.com/buyonline/pixcel-crush-silk-saree/kid/ef_pc_clot0v154pod00857",
    },
    {
      id: "CLOTHING07949",
      name: "Sunset Bloom Batik Saree",
      price: 4950,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/shops/specialGifts/productImages/1754538451793_dsc00972.jpg",
      url: "https://www.kapruka.com/buyonline/sunset-bloom-batik-saree/kid/clothing07949",
    },
  ],
  men: [
    {
      id: "EF_PC_CLOT0V160POD02119FDP",
      name: "Adam Cotton Shirt For Men - Olive",
      price: 4950,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://cdn.shopify.com/s/files/1/0536/5851/7700/files/3G9A0352copy.jpg?v=1761914871&width=330",
      url: "https://www.kapruka.com/buyonline/adam-cotton-shirt-for-men-olive/kid/ef_pc_clot0v160pod02119fdp",
    },
    {
      id: "EF_PC_CLOT0V160POD02118FDP",
      name: "Adam Cotton Shirt For Men - Navy Blue",
      price: 4950,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://cdn.shopify.com/s/files/1/0536/5851/7700/files/3G9A0309_copy.jpg?v=1761913371&width=330",
      url: "https://www.kapruka.com/buyonline/adam-cotton-shirt-for-men-navy/kid/ef_pc_clot0v160pod02118fdp",
    },
    {
      id: "EF_PC_CLOT0V2248POD01280P",
      name: "Signature Men's Leaf Green Polo T-Shirt",
      price: 3300,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc00971/clot0v2248p01280/clot0v2248p01280_1.jpg",
      url: "https://www.kapruka.com/buyonline/signature-men-s-leaf-green-reg/kid/ef_pc_clot0v2248pod01280p",
    },
    {
      id: "EF_PC_CLOT0V2248POD01253",
      name: "Signature Men's Regular Fit Green Polo T-Shirt",
      price: 3300,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc00971/clot0v2248p01253/clot0v2248p01253_1.jpg",
      url: "https://www.kapruka.com/buyonline/signature-men-s-regular-fit-gr/kid/ef_pc_clot0v2248pod01253",
    },
    {
      id: "EF_PC_CLOT0V2248POD01283P",
      name: "Signature Men's Olive Drab Green Polo T-Shirt",
      price: 3300,
      currency: "LKR",
      in_stock: true,
      stock_level: "low",
      image_url:
        "https://static2.kapruka.com/product-image/width=330,quality=93,f=auto/https://partnercentral.kapruka.com/kapruka-pc/assets/images/product/pc00971/clot0v2248p01283/clot0v2248p01283_1.jpg",
      url: "https://www.kapruka.com/buyonline/signature-men-s-olive-drab-gre/kid/ef_pc_clot0v2248pod01283p",
    },
  ],
};
