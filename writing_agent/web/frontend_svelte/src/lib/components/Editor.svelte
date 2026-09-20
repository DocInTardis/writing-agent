<script lang="ts">
  import StructuredEditor from './StructuredEditor.svelte'

  let {
    showToolbar = true,
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    onblockai,
    onblockdrag,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    onblockai?: () => void
    onblockdrag?: (active: boolean) => void
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
  {onblockdrag}
  {ontoolbarstate}
/>
