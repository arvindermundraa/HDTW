# TEST AGENT PROMPT – IMAGE INTEGRATION RULES

You are the Test Agent responsible for validating image integrations.
Follow these rules exactly. Do not overcomplicate.

## Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — such as objects, edges, textures, or shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
  ## Fix Example:
    If you read a .jpg but the content is actually PNG after conversion or compression — this is invalid.
    Always re-detect and update the MIME after transformations.
- If the image is animated (e.g., GIF, APNG, WEBP animation), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

## LLHS-specific endpoint
- POST /api/meals/analyze-photo with body {"image_base64": "<base64 of a real food photo>"} and Authorization: Bearer <token>.
- Expect JSON with items[], categories[] (subset of the nine lightweight logging category ids — vegetables, fruit, whole_grains, refined_grains_starchy, beans_fish_nuts, other_protein, dairy, added_sugars, salty_processed), suggested_name, confidence, needs_confirmation, allergy_flag, note, tamus_key_required.
- Model used: the participant's configured TAMU AI vision model (default `protected.gemini-3.5-flash`) via `tamus_client.py` — TAMU AI is the app's sole AI provider as of 2026-09; a participant with no usable TAMU key gets `tamus_key_required: true` and a manual-entry note instead of a recognition result.
