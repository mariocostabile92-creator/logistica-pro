export const authState = { status: "loading", user: null };

export function setSession(user) {
  authState.status = user ? "authenticated" : "anonymous";
  authState.user = user;
  document.body.dataset.authState = authState.status;
  document.body.dataset.role = user?.role || "";
  document.body.dataset.canWrite = String(user?.permissions?.includes("admin:write") || false);
}

export const can = permission =>
  Boolean(authState.user?.permissions?.includes(permission));
