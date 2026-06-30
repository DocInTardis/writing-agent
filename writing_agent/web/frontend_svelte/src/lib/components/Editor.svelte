<script lang="ts">
  import EditorWorkbench from './EditorWorkbench.svelte'

  let {
    showToolbar = true,
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    ontoolbarstate?: (state: any) => void
  } = $props()
</script>

<EditorWorkbench
  {showToolbar}
  {paper}
  {lockEditing}
  {onblockedit}
  {onblockselect}
  {ontoolbarstate}
/>
