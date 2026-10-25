"use client";

import { Result } from "antd";
import { useParams } from "next/navigation";

import { ResourceForm } from "@/components/staff/ResourceForm";
import { ResourceList } from "@/components/staff/ResourceList";
import { UI } from "@/lib/i18n";
import { useSession } from "@/lib/refine/session";
import { findResource, tr } from "@/lib/resources";

/** Resolves /<module>/<resource>[/create|/<id>/edit] to its registry entry. */
export function ResourcePage({ view }: { view: "list" | "create" | "edit" }) {
  const params = useParams<{ module: string; resource: string; id?: string }>();
  const { lang, can, allBranches } = useSession();
  const def = findResource(params.module, params.resource);

  if (!def) return <Result status="404" title={tr(UI.notFound, lang)} />;
  if (view !== "list" && allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;
  const needed = view === "list" ? `${def.perm}.view` : `${def.perm}.manage`;
  if (!can(needed)) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  if (view === "list") return <ResourceList def={def} />;
  return <ResourceForm def={def} mode={view} id={params.id} />;
}
