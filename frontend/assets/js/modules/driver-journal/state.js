export const initialState = () => ({
  step: 0, operationType: null, configuration: null, asset: null,
  sessionId: null, token: null, media: [], submitting: false, receipt: null,
  sharedSession: null, progressMarked: false,
  warnings: [], minStep: 0, source: "shared_link", accessToken: null,
  clientSubmissionId: crypto.randomUUID(),
});
export const state = initialState();
export function resetState() { Object.assign(state, initialState()); }
