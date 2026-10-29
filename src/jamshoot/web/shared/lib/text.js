export const title = (value) =>
  value.replaceAll("-", " ").replace(/^./, (char) => char.toUpperCase());
// A camelCase key as lowercase words: "deviceFrame" → "device frame".
export const words = (key) => key.replace(/[A-Z]/g, (char) => ` ${char.toLowerCase()}`);
