import { getDspDailySnapshot as requestSnapshot } from "../../api.js?v=53";


export async function getDspDailySnapshot(
  operationDate,
  options = {},
) {
  return requestSnapshot(operationDate, options);
}
