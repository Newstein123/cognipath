"use client";

import { useParams } from "next/navigation";
import { param } from "@/lib/api";
import { TutorBox } from "@/components/TutorBox";
import { PageHead } from "@/components/ui";

export default function TutorPage() {
  const id = param(useParams().id);
  return (
    <>
      <PageHead eyebrow="Tutor" title="Ask the tutor" />
      <TutorBox learnerId={id} />
    </>
  );
}
