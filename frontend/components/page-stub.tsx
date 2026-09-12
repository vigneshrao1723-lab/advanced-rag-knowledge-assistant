import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Placeholder for a route whose product functionality is scoped to a later
 * issue (see docs/ARCHITECTURE.md "Target routes"). Application Foundation
 * (Issue #1) only proves the route/shell exists — it deliberately does not
 * implement the feature.
 */
export function PageStub({
  title,
  description,
  issue,
}: {
  title: string;
  description: string;
  issue: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground text-sm">
          Not yet implemented — planned for {issue}.
        </p>
      </CardContent>
    </Card>
  );
}
