export const initialState = () => ({
  step: 0, operationType: null, configuration: null, asset: null,
  sessionId: null, token: null, media: [], submitting: false, receipt: null,
  clientSubmissionId: crypto.randomUUID(),
});
export const state = initialState();
export function resetState() { Object.assign(state, initialState()); }
