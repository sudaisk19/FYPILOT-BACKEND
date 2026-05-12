/**
 * @module Jury
 *
 * Data-driven coverage from `test-data/jury.data.json` → `endpoint_matrix`.
 * Inventory: `app/api/http/jury_matching.py` mounted under `/api/jury-matching`.
 *
 * AI/LLM routes are explicitly present as skipped rows in matrix.
 */

import juryData from "../../test-data/jury.data.json";
import {
  registerEndpointMatrix,
  type MatrixRow,
} from "../_helpers/endpoint-runner";

registerEndpointMatrix(
  "Jury HTTP API",
  juryData.endpoint_matrix as MatrixRow[],
  juryData.ids as Record<string, string>,
);
