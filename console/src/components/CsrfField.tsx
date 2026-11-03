"use client";

import { useEffect, useState } from "react";
import { readCsrfToken } from "@/lib/csrf-client";

/** Hidden input carrying the double-submit CSRF token into a Server Action. */
export function CsrfField() {
  const [token, setToken] = useState("");
  useEffect(() => setToken(readCsrfToken()), []);
  return <input type="hidden" name="csrf" value={token} />;
}
