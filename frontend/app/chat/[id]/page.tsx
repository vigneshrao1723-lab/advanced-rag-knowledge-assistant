import { PageStub } from "@/components/page-stub";

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <PageStub
      title={`Chat ${id}`}
      description="Grounded conversation with citations."
      issue="Issue #4 (Hybrid RAG Pipeline) / Issue #5 (Product Experience)"
    />
  );
}
