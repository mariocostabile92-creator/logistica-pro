export class ApiError extends Error {
  constructor(message, { status = 0, code = null, detail = null, cause = null } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}


export class ExpectedUserError extends Error {
  constructor(message) {
    super(message);
    this.name = "ExpectedUserError";
  }
}


export function isExpectedApiError(
  error,
  { statuses = [], codes = [], messages = [] } = {},
) {
  if (!(error instanceof ApiError)) return false;
  if (statuses.includes(error.status)) {
    if (!codes.length && !messages.length) return true;
    if (error.code && codes.includes(error.code)) return true;
    return messages.some((message) => (
      error.message.toLocaleLowerCase("it").includes(
        message.toLocaleLowerCase("it"),
      )
    ));
  }
  return false;
}


export function userMessageForError(
  error,
  fallback = "Non è stato possibile completare l'operazione.",
) {
  if (error instanceof ExpectedUserError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    if (error.status >= 500) {
      return "Il servizio ha riscontrato un problema. Riprova tra poco.";
    }
    return error.message || fallback;
  }
  if (error instanceof TypeError) {
    return "Il servizio non è raggiungibile. Controlla la connessione e riprova.";
  }
  return fallback;
}


export function reportUnexpectedError(context, error) {
  const diagnostic = error instanceof ApiError
    ? { context, status: error.status, code: error.code }
    : { context, type: error?.name || "Error" };
  console.error("[Operations Engine] Errore imprevisto", diagnostic);
}


export function userErrorPresentation(
  context,
  error,
  {
    statuses = [400, 404, 409, 413, 415, 422],
    codes = [],
    messages = [],
    fallback,
  } = {},
) {
  const expected = error instanceof ExpectedUserError
    || isExpectedApiError(error, { statuses, codes, messages });
  if (!expected) reportUnexpectedError(context, error);
  return {
    message: userMessageForError(error, fallback),
    tone: expected ? "warning" : "error",
  };
}
