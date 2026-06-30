<script lang="ts">
  import EditorWorkbench from './EditorWorkbench.svelte'

  export let showToolbar = true
  export let paper = true
  export let lockEditing = false
</script>

<EditorWorkbench
  {showToolbar}
  {paper}
  {lockEditing}
  on:blockedit
  on:blockselect
  on:toolbarstate
/>
