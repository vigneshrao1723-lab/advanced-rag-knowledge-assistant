import { BackendStatus } from "@/components/backend-status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Advanced RAG Knowledge Assistant</CardTitle>
          <CardDescription>
            Application foundation — no product features are implemented yet. See{" "}
            <code>PROJECT_STATE.md</code> for real, current status.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Upload knowledge → retrieve evidence → receive grounded answer → inspect citations.
        </CardContent>
      </Card>

      <BackendStatus />
    </div>
  );
}
