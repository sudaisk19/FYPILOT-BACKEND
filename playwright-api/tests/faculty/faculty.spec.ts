/**
 * @module Faculty
 *
 * Data-driven coverage from `test-data/faculty.data.json` → `endpoint_matrix`.
 * Inventory: `app/api/http/faculty_*.py`, `supervisor_*.py`, and router mounts under `/api`.
 *
 * Skipped rows in matrix are explicitly tagged (AI/LLM or multipart-only endpoints).
 */

import facultyData from "../../test-data/faculty.data.json";
import {
  registerEndpointMatrix,
  type MatrixRow,
} from "../_helpers/endpoint-runner";

registerEndpointMatrix(
  "Faculty HTTP API",
  facultyData.endpoint_matrix as MatrixRow[],
  facultyData.ids as Record<string, string>,
);
