"use client";

import { useParams } from "next/navigation";
import { param } from "@/lib/api";
import { TutorBox } from "@/components/TutorBox";

export default function TutorPage() {
  const id = param(useParams().id);
  return (
    <>
      <h1>AI tutor</h1>
      <TutorBox learnerId={id} />
    </>
  );
}
