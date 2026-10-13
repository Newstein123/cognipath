"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type Activity } from "@/lib/api";
import { ActivityRunner } from "@/components/ActivityRunner";
import { ErrorBox, Loading } from "@/components/ui";

const TYPE_HEADING: Record<string, string> = {
  diagnostic: "Check what you know",
  exercise: "Practice",
  apply: "Independent challenge",
  mission: "Mission",
};

export default function ActivityPage() {
  const params = useParams();
  const id = param(params.id);
  const aid = param(params.aid);
  const [activity, setActivity] = useState<Activity | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.activity(aid).then(setActivity).catch((e) => setError(e.message));
  }, [aid]);

  if (error) return <ErrorBox error={error} />;
  if (!activity) return <Loading stages={["Loading…"]} />;

  return (
    <>
      <p className="small muted" style={{ marginBottom: 4 }}>{TYPE_HEADING[activity.type] ?? activity.type}</p>
      <ActivityRunner learnerId={id} activity={activity} />
    </>
  );
}
