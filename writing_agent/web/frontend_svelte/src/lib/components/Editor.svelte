<script lang="ts">
  import StructuredEditor from './StructuredEditor.svelte'

  let {
    showToolbar = true,
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    onblockai,
    ontextai,
    onblockdrag,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    onblockai?: () => void
    ontextai?: (payload: { text: string; from: number; to: number }) => void
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
  {ontextai}
  {onblockdrag}
  {ontoolbarstate}
/>
