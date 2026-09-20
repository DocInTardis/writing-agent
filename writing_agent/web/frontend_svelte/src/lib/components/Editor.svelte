<script lang="ts">
  import StructuredEditor from './StructuredEditor.svelte'

  let {
    showToolbar = true,
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    onblockai,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    onblockai?: () => void
    ontoolbarstate?: (state: any) => void
  } = $props()

</script>

<StructuredEditor
  {showToolbar}
  {paper}
  {lockEditing}
  {onblockedit}
  {onblockselect}
  {onblockai}
  {ontoolbarstate}
/>
