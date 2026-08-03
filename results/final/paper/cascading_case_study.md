# Cascading Repair Case Study

**Case:** Missing dependency chain

**Initial configuration:** 1 selected mod(s), Minecraft 1.20.1, fabric.

**Initial issue:** missing_dependency.

**Step 1:** add_dependency `cascade-b`.

After this action: missing_dependency.

**Step 2:** add_dependency `cascade-c`.

After this action: missing_dependency.

**Step 3:** add_dependency `cascade-d`.

After this action: no remaining issues.

**Final result:** Compatible.

**Why the complete plan was preferred:** The weighted solver evaluated the whole 3-action sequence at total cost 3, rather than stopping after the first locally useful dependency addition.
