import Base64 from "./Base64";
import { SERVER_URL, REQUEST_TIMEOUT_MS } from "../utils/config";

const URL = SERVER_URL;

/** fetch with a timeout, so a dead server fails fast instead of hanging. */
async function fetchWithTimeout(input: string, init?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function arrayBufferToBase64(buffer: ArrayBuffer) {
  let binary = "";
  const bytes = [].slice.call(new Uint8Array(buffer));
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return Base64.btoa(binary);
}

function ping() {
  return fetchWithTimeout(URL + "/ping")
    .then((res) => res.json())
    .catch((e) => {
      console.error("Ping error:", e);
      throw e;
    });
}

async function cut(imageURI: string) {
  const formData = new FormData();
  formData.append("data", {
    uri: imageURI,
    name: "photo",
    type: "image/jpg",
  } as any);

  try {
    console.log("> sending to server...");
    const res = await fetchWithTimeout(URL + "/cut", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    console.log("> converting...");
    const buffer = await res.arrayBuffer();
    const base64Flag = "data:image/png;base64,";
    const imageStr = arrayBufferToBase64(buffer);
    return base64Flag + imageStr;
  } catch (error) {
    console.error("Cut error:", error);
    throw error;
  }
}

async function paste(imageURI: string) {
  const formData = new FormData();
  formData.append("data", {
    uri: imageURI,
    name: "photo",
    type: "image/jpg",
  } as any);

  try {
    const response = await fetchWithTimeout(URL + "/paste", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`);
    }

    return response.json();
  } catch (error) {
    console.error("Paste error:", error);
    throw error;
  }
}

export default {
  ping,
  cut,
  paste,
};
