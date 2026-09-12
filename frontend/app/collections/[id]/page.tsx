import { PageStub } from "@/components/page-stub";

export default async function CollectionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <PageStub
      title={`Collection ${id}`}
      description="Documents scoped to this collection."
      issue="Issue #5 (Product Experience)"
    />
  );
}
