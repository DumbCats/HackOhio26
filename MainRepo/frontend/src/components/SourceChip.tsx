import type { Source } from "../types";
import { SOURCE_LABEL } from "../format";

export function SourceChip({ source, muted }: { source: Source; muted?: boolean }) {
  return (
    <span className={`chip chip-${source}${muted ? " chip-muted" : ""}`} title="Where this number comes from">
      {SOURCE_LABEL[source] ?? source}
    </span>
  );
}
