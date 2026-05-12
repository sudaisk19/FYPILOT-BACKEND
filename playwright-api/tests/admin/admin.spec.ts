/**
 * @module Admin
 *
 * Data-driven coverage from `test-data/admin.data.json` → `endpoint_matrix`.
 * Inventory: `app/api/http/admin_*.py` and mounted routes under `/api` + `/api/admins`.
 *
 * Skipped rows in matrix are explicitly tagged (multipart-only or non-JSON endpoints).
 */

import adminData from "../../test-data/admin.data.json";
import {
  registerEndpointMatrix,
  type MatrixRow,
} from "../_helpers/endpoint-runner";

registerEndpointMatrix(
  "Admin HTTP API",
  adminData.endpoint_matrix as MatrixRow[],
  adminData.ids as Record<string, string>,
);
