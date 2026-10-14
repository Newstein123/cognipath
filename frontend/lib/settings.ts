// Per-course display settings, set when a learner's course is known.
// Inline $…$ maths is on for maths courses, off where prose has prices ("$500").
let inlineMath = process.env.NEXT_PUBLIC_INLINE_MATH === "1";

export const getInlineMath = () => inlineMath;
export function setInlineMath(on: boolean) { inlineMath = on; }
