import { Suspense } from "react";

import { ResourcePage } from "@/components/staff/ResourcePage";

export default function Page() {
  return (
    <Suspense>
      <ResourcePage view="create" />
    </Suspense>
  );
}
