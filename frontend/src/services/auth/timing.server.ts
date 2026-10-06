/** Safe opt-in Preview diagnostics. Never accepts scope, identities or payload. */
export function numericServerTimings(header: string) {
  const durations: Record<string, number> = {};
  for (const part of header.split(",")) {
    const match =
      /^(auth|bq|wif|upstream|serialization|api_total|bff|bff_serialization);dur=(\d+(?:\.\d+)?)$/.exec(
        part.trim(),
      );
    if (match && Number.isFinite(Number(match[2])))
      durations[match[1]] = Number(match[2]);
  }
  return durations;
}
