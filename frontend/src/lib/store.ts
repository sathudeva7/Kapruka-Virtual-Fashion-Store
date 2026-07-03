import { create } from "zustand";
import { FEATURED } from "./featured";

export type Section = "men" | "women";
export type Lang = "en" | "ta" | "si";
export type Connection = "idle" | "connecting" | "live" | "recording" | "thinking";

// Mirrors the backend `_card()` shape (main.py).
export interface ProductItem {
  id?: string;
  name?: string;
  summary?: string;
  price?: number;
  currency?: string;
  image_url?: string;
  in_stock?: boolean;
  stock_level?: string;
  url?: string;
  group?: string | null;
}

// Mirrors a line in the backend cart (tools/cart.py).
export interface CartLine {
  product_id: string;
  name: string;
  category?: string;
  unit_price: number;
  quantity: number;
  image_url?: string;
}

export interface CartState {
  items: CartLine[];
  count: number;
  total: number;
  currency: string;
}

// Buyer + delivery details typed into the on-screen form (mirrors the state
// keys checkout/before_checkout_tool reads).
export interface CheckoutDetails {
  name: string;
  phone: string;
  address: string;
  city: string;
  date: string;
  instructions?: string;
}

export interface OrderItem {
  order_ref?: string;
  checkout_url?: string;
  expires_at?: string;
  grand_total?: number;
  currency?: string;
}

export interface TryonItem {
  url: string;
  product_id?: string;
  product_name?: string;
}

export interface TrackingStep {
  step: string;
  timestamp?: string;
}

// Mirrors the backend tracking card (tools/callbacks.py `_tracking_card`).
export interface TrackingItem {
  order_number?: string;
  status?: string;
  status_display?: string;
  delivery_date?: string;
  order_date?: string;
  amount?: string | number;
  currency?: string;
  recipient_name?: string;
  recipient_city?: string;
  comments?: string;
  progress?: TrackingStep[];
  live_tracking_available?: boolean;
  has_delivery_photo?: boolean;
  has_delivery_video?: boolean;
}

export type TryOnStatus = "idle" | "generating" | "ready" | "error";

export interface TryOnState {
  active: boolean; // are we inside the fitting-room try-on experience
  status: TryOnStatus;
  userPhotoUrl: string | null; // client-side blob URL of the uploaded photo
  resultUrl: string | null; // /static/generated/... of the generated look
  productName: string | null;
  error: string | null;
}

// A one-shot teleport command consumed by PlayerControls.
export interface Teleport {
  x: number;
  z: number;
  yaw: number;
}

// Analog movement intent from the on-screen joystick (touch). x = turn
// (-1 left … +1 right), y = walk (-1 back … +1 forward). PlayerControls reads it
// each frame and applies it alongside the keyboard.
export interface MoveVec {
  x: number;
  y: number;
}

interface StoreState {
  // world
  section: Section; // section the player is currently standing in
  nearAssistant: boolean;
  move: MoveVec; // joystick movement intent

  // data driven by the voice/data client
  productsBySection: Record<Section, ProductItem[]>;
  // when true, the next product to arrive starts a fresh wall (new search)
  freshBatch: boolean;
  selectedProduct: ProductItem | null;
  orders: OrderItem[];
  tracking: TrackingItem[];
  tryonImages: TryonItem[];

  // shopping cart
  cart: CartState;
  cartOpen: boolean;

  // typed checkout details form
  checkout: CheckoutDetails;
  checkoutOpen: boolean;
  checkoutSaved: boolean;

  // conversation surface
  userCaption: string;
  userPartial: string; // interim (still-talking) transcript; cleared on final
  botCaption: string;
  toolStatus: string | null;
  error: string | null;
  captionsHidden: boolean; // user dismissed the on-screen subtitles

  // voice
  lang: Lang;
  connection: Connection;

  // fitting-room virtual try-on
  tryOn: TryOnState;
  teleport: Teleport | null;
  enlarge: string | null; // url of an image shown full-screen, or null

  // actions
  setSection: (s: Section) => void;
  setNear: (n: boolean) => void;
  setMove: (m: MoveVec) => void;
  setCaptionsHidden: (h: boolean) => void;
  setSelected: (p: ProductItem | null) => void;
  setLang: (l: Lang) => void;
  setConnection: (c: Connection) => void;
  beginBatch: () => void;
  endBatch: () => void;
  seedFeatured: () => void;
  addProduct: (item: ProductItem) => void;
  addOrder: (o: OrderItem) => void;
  addTracking: (t: TrackingItem) => void;
  removeTracking: (orderNumber?: string) => void;
  addTryon: (t: TryonItem) => void;
  setCart: (c: CartState) => void;
  setCartOpen: (open: boolean) => void;
  setCheckout: (d: CheckoutDetails) => void;
  setCheckoutOpen: (open: boolean) => void;
  setCheckoutSaved: (saved: boolean) => void;
  setUserCaption: (text: string) => void;
  setUserPartial: (text: string) => void;
  appendBotCaption: (text: string) => void;
  newBotTurn: () => void;
  setToolStatus: (s: string | null) => void;
  setError: (e: string | null) => void;
  // try-on actions
  startTryOn: (userPhotoUrl: string, productName: string | null) => void;
  setTryOnResult: (resultUrl: string) => void;
  setTryOnError: (msg: string) => void;
  exitTryOn: () => void;
  requestTeleport: (t: Teleport) => void;
  clearTeleport: () => void;
  setEnlarge: (url: string | null) => void;
}

const IDLE_TRYON: TryOnState = {
  active: false,
  status: "idle",
  userPhotoUrl: null,
  resultUrl: null,
  productName: null,
  error: null,
};

export const useStore = create<StoreState>((set, get) => ({
  section: "men",
  nearAssistant: false,
  move: { x: 0, y: 0 },

  productsBySection: { men: [], women: [] },
  freshBatch: false,
  selectedProduct: null,
  orders: [],
  tracking: [],
  tryonImages: [],

  cart: { items: [], count: 0, total: 0, currency: "LKR" },
  cartOpen: false,

  checkout: { name: "", phone: "", address: "", city: "", date: "", instructions: "" },
  checkoutOpen: false,
  checkoutSaved: false,

  userCaption: "",
  userPartial: "",
  botCaption: "",
  toolStatus: null,
  error: null,
  captionsHidden: false,

  lang: "en",
  connection: "idle",

  tryOn: IDLE_TRYON,
  teleport: null,
  enlarge: null,

  setSection: (s) => {
    if (get().section !== s) set({ section: s });
  },
  setNear: (n) => set({ nearAssistant: n }),
  setMove: (m) => set({ move: m }),
  setCaptionsHidden: (h) => set({ captionsHidden: h }),
  setSelected: (p) => set({ selectedProduct: p }),
  setLang: (l) => set({ lang: l }),
  setConnection: (c) => set({ connection: c }),

  // Mark the start of a new search; the next arriving product replaces the wall
  // of whatever section it lands in (rather than piling onto the old results).
  beginBatch: () => set({ freshBatch: true }),

  // Close out a batch that produced no products (empty/failed search) so the
  // pending freshBatch flag doesn't later wipe the wall when an unrelated
  // product arrives. The current wall (seeded or previous results) stays put.
  endBatch: () => set({ freshBatch: false }),

  // Fill the racks with the curated default products on first load, so neither
  // wall ever shows the empty-state placeholder. Only seeds a section that's
  // still empty — a real search/voice result (which sets freshBatch) replaces
  // the wall as usual, so this never fights live results.
  seedFeatured: () =>
    set((st) => {
      const next = { ...st.productsBySection };
      let changed = false;
      (Object.keys(next) as Section[]).forEach((sec) => {
        if (next[sec].length === 0 && FEATURED[sec]?.length) {
          next[sec] = FEATURED[sec].slice(0, 10);
          changed = true;
        }
      });
      return changed ? { productsBySection: next } : {};
    }),

  // New products land on the racks of whichever section the player is in. The
  // first product of a fresh batch clears that section first; the list is capped
  // so the wall stays a tidy ≤2-row grid.
  addProduct: (item) =>
    set((st) => {
      const section = st.section;
      const base = st.freshBatch ? [] : st.productsBySection[section];
      // de-dupe by id within the section
      if (item.id && base.some((p) => p.id === item.id)) {
        return { freshBatch: false };
      }
      const next = [...base, item].slice(-10);
      return {
        freshBatch: false,
        productsBySection: { ...st.productsBySection, [section]: next },
      };
    }),
  addOrder: (o) => set((st) => ({ orders: [...st.orders, o] })),
  // De-dupe by order number so a re-track of the same order replaces (not stacks)
  // its card with the latest status.
  addTracking: (t) =>
    set((st) => {
      const rest = t.order_number
        ? st.tracking.filter((x) => x.order_number !== t.order_number)
        : st.tracking;
      return { tracking: [...rest, t] };
    }),
  removeTracking: (orderNumber) =>
    set((st) => ({
      tracking: orderNumber
        ? st.tracking.filter((t) => t.order_number !== orderNumber)
        : [],
    })),
  addTryon: (t) => set((st) => ({ tryonImages: [...st.tryonImages, t] })),
  setCart: (c) => set({ cart: c }),
  setCartOpen: (open) => set({ cartOpen: open }),
  setCheckout: (d) => set({ checkout: d }),
  setCheckoutOpen: (open) => set({ checkoutOpen: open }),
  setCheckoutSaved: (saved) => set({ checkoutSaved: saved }),

  setUserCaption: (text) => set({ userCaption: text, userPartial: "" }),
  setUserPartial: (text) => set({ userPartial: text }),
  appendBotCaption: (text) => set((st) => ({ botCaption: st.botCaption + text })),
  newBotTurn: () => set({ botCaption: "" }),
  setToolStatus: (s) => set({ toolStatus: s }),
  setError: (e) => set({ error: e }),

  // --- virtual try-on ---
  startTryOn: (userPhotoUrl, productName) =>
    set({
      selectedProduct: null,
      enlarge: null,
      tryOn: {
        active: true,
        status: "generating",
        userPhotoUrl,
        resultUrl: null,
        productName,
        error: null,
      },
    }),
  setTryOnResult: (resultUrl) =>
    set((st) => ({ tryOn: { ...st.tryOn, status: "ready", resultUrl, error: null } })),
  setTryOnError: (msg) =>
    set((st) => ({ tryOn: { ...st.tryOn, status: "error", error: msg } })),
  exitTryOn: () => set({ tryOn: IDLE_TRYON, enlarge: null }),
  requestTeleport: (t) => set({ teleport: t }),
  clearTeleport: () => set({ teleport: null }),
  setEnlarge: (url) => set({ enlarge: url }),
}));

// Expose the store on window for debugging / automated smoke tests.
if (typeof window !== "undefined") {
  (window as unknown as { kaprukaStore: typeof useStore }).kaprukaStore = useStore;
}
