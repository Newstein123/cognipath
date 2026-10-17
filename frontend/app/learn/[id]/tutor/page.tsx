"use client";

import { useParams } from "next/navigation";
import { param } from "@/lib/api";
import { TutorChat } from "@/components/TutorChat";
import { PageHead } from "@/components/ui";

/** The same conversation as Home's tutor panel (lib/tutorChat), given the whole page. */
export default function TutorPage() {
  const id = param(useParams().id);
  return (
    <div className="tutor-page">
      <PageHead eyebrow="Tutor" title="Ask the tutor" />
      <TutorChat variant="page" learnerId={id} title="Conversation" />
    </div>
  );
}
