import { PageStub } from "@/components/page-stub";

export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <PageStub
      title={`Document ${id}`}
      description="Document viewer with citation deep-linking."
      issue="Issue #5 (Product Experience)"
    />
  );
}
