# Sticky Note

The **Sticky Note** node adds rich markdown notes to the canvas. It is not executed—use it for documentation, instructions, reference images, or workflow notes.

## Overview

| Property | Value |
|----------|-------|
| Inputs | 0 |
| Outputs | 0 |
| Output | N/A (not executed) |

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string | Node identifier (camelCase) |
| `stickyTitle` | string | Display title shown at the top of the sticky note. |
| `stickyColor` | string | Background color: `yellow`, `sky`, `emerald`, `rose`, `violet`, or `zinc`. |
| `note` | string | Markdown content. Double-click to edit on canvas. Supports links and image markdown such as `![Alt](https://example.com/image.png)`. |

## Example

```json
{
  "type": "sticky",
  "data": {
    "label": "workflowNotes",
    "stickyTitle": "Launch Notes",
    "stickyColor": "sky",
    "note": "![Heym Logo](https://heym.run/og-image.png)\n\n[Heym.run](https://heym.run)"
  }
}
```

## Related

- [Node Types](../reference/node-types.md) – Overview of all node types
- [Workflow Organization](../reference/workflow-organization.md) – Organize workflows
