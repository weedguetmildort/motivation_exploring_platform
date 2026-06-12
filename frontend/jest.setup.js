// frontend/jest.setup.js
import "@testing-library/jest-dom";
import { TextEncoder, TextDecoder } from "util";
import { randomUUID } from "crypto";

// jsdom does not implement ResizeObserver, but several components
// (e.g. MarkdownMessage's KaTeX auto-fit) use it.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom does not provide TextEncoder/TextDecoder, used by lib/chat.ts when
// decoding SSE streams.
if (typeof global.TextEncoder === "undefined") {
  global.TextEncoder = TextEncoder;
}
if (typeof global.TextDecoder === "undefined") {
  global.TextDecoder = TextDecoder;
}

// jsdom does not implement Element.scrollTo, used by ChatBox to keep the
// message list scrolled to the bottom.
if (typeof Element.prototype.scrollTo === "undefined") {
  Element.prototype.scrollTo = () => {};
}

// jsdom's Crypto implementation does not provide randomUUID, used by ChatBox
// to generate message ids.
if (typeof global.crypto.randomUUID === "undefined") {
  global.crypto.randomUUID = randomUUID;
}
