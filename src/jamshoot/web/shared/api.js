// Requests carry the session token; a failed one throws the server's message.
// `raw` sends bytes as is, `serialized` sends JSON text that is already encoded;
// `withHeaders` returns `{ body, headers }` instead of the body alone.
export function createAPI(token, fetcher = fetch) {
  return async function api(path, data, options = {}) {
    const response = await send(token, fetcher, path, data, options);
    // PNG previews and .zip archives arrive as blobs.
    const body = response.headers.get("Content-Type")?.includes("application/json")
      ? await response.json()
      : await response.blob();
    return options.withHeaders ? { body, headers: response.headers } : body;
  };
}

function validationMessage(details) {
  const fields = details.slice(0, 5).map(({ path, message }) => `${path || "Project"}: ${message}`);
  if (details.length > 5)
    fields.push(`And ${details.length - 5} more. Correct these fields and try again.`);
  return `Check these project fields:\n${fields.join("\n")}`;
}

async function responseError(response) {
  if (response.status >= 500)
    return new Error(
      "Studio could not complete this request. Try again; if it keeps failing, check the Studio terminal.",
    );
  const failure = await response.json().catch(() => ({}));
  const details = failure.error?.details;
  return new Error(
    Array.isArray(details) && details.length
      ? validationMessage(details)
      : failure.error?.message || "This request could not be completed. Try again.",
  );
}

async function send(token, fetcher, path, data, { raw, serialized, signal, method }) {
  const request = { signal, method, headers: { "X-JamShoot-Token": token } };
  if (data !== undefined) {
    request.method ||= "POST";
    request.headers["Content-Type"] = raw ? "application/octet-stream" : "application/json";
    request.body = raw || serialized ? data : JSON.stringify(data);
  }
  let response;
  try {
    response = await fetcher(path, request);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Cannot reach Studio. Check that it is still running, then try again.");
  }
  if (!response.ok) throw await responseError(response);
  return response;
}
