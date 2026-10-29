import { title } from "../lib/text.js";

const PLATFORM_NAMES = {
  mac: "Mac",
  iphone: "iPhone",
  "iphone-duo": "Duo",
  ipad: "iPad",
  custom: "Custom",
};
export const platformName = (platform) => PLATFORM_NAMES[platform] || title(platform);
