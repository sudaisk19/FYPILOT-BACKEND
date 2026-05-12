/**
 * @module Student
 *
 * Data-driven coverage from `test-data/student.data.json` → `endpoint_matrix`.
 * Inventory: `app/api/http/student_*.py` + `router.py` mounts under `/api`.
 *
 * Skipped elsewhere: multipart uploads, LLM `POST .../messages`, import-template
 * with extraction, whiteboards state, progress routes without `TEST_GROUP_ID`.
 */

import studentData from "../../test-data/student.data.json";
import {
  registerEndpointMatrix,
  type MatrixRow,
} from "../_helpers/endpoint-runner";

registerEndpointMatrix(
  "Student HTTP API",
  studentData.endpoint_matrix as MatrixRow[],
  studentData.ids as Record<string, string>,
);
