<script lang="ts">
  import { sourceText, docIr, docIrDirty, generating } from '../stores'
  import { renderDocument } from '../utils/markdown'

  let previewHtml = ''
  $: {
    const hasDocIr = Boolean($docIr && typeof $docIr === 'object')
    const preferText = !hasDocIr
    previewHtml = renderDocument($sourceText || '', $docIr, preferText)
  }
</script>

<div class="panel preview">
  <div class="panel-title">实时预览</div>
  <div class="preview-body">{@html previewHtml}</div>
</div>

<style>
  .preview-body {
    background: #f0f2f5;
    padding: 20px 0 32px;
  }

  .preview-body :global(.wa-doc) {
    max-width: 820px;
    margin: 0 auto;
    padding: 56px 64px;
    background: #fff;
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
    border: 1px solid #e2e8f0;
    font-family: "Times New Roman", "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
    color: #1f2933;
  }

  .preview-body :global(.wa-doc .wa-header),
  .preview-body :global(.wa-doc .wa-footer) {
    font-size: 12px;
    color: #94a3b8;
    text-align: center;
    letter-spacing: 0.04em;
  }

  .preview-body :global(.wa-doc .wa-header) {
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 6px;
    margin-bottom: 18px;
    min-height: 14px;
  }

  .preview-body :global(.wa-doc .wa-header:empty) {
    border-bottom: none;
    padding-bottom: 0;
    margin-bottom: 0;
    min-height: 0;
  }

  .preview-body :global(.wa-doc .wa-footer) {
    border-top: 1px solid #e2e8f0;
    padding-top: 6px;
    margin-top: 24px;
  }

  .preview-body :global(.wa-doc .wa-title) {
    text-align: center;
    margin-bottom: 22px;
    font-size: 26px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  .preview-body :global(.wa-doc h1),
  .preview-body :global(.wa-doc h2),
  .preview-body :global(.wa-doc h3) {
    margin: 18px 0 10px;
    font-weight: 600;
  }

  .preview-body :global(.wa-doc p) {
    margin: 6px 0;
    line-height: 1.8;
    text-align: justify;
  }

  .preview-body :global(.wa-doc ul),
  .preview-body :global(.wa-doc ol) {
    padding-left: 22px;
    margin: 6px 0;
  }

  .preview-body :global(.wa-doc li) {
    line-height: 1.7;
    margin: 2px 0;
  }

  .preview-body :global(.wa-doc figure) {
    margin: 14px 0;
    text-align: center;
  }

  .preview-body :global(.wa-doc .wa-figure-box),
  .preview-body :global(.wa-doc .wa-table-box) {
    height: 140px;
    border: 1px dashed #94a3b8;
    color: #64748b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }

  .preview-body :global(.wa-doc table) {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 14px;
  }

  .preview-body :global(.wa-doc th),
  .preview-body :global(.wa-doc td) {
    border: 1px solid #cbd5e1;
    padding: 6px 8px;
  }

  .preview-body :global(.wa-doc figcaption) {
    margin-top: 6px;
    font-size: 12px;
    color: #64748b;
  }

  @media (max-width: 900px) {
    .preview-body :global(.wa-doc) {
      margin: 0 12px;
      padding: 32px 20px;
    }
  }

  .preview-body :global(h1),
  .preview-body :global(h2),
  .preview-body :global(h3) {
    margin: 16px 0 8px;
  }

  .preview-body :global(p) {
    margin: 6px 0;
    line-height: 1.7;
  }

  .preview-body :global(ol),
  .preview-body :global(ul) {
    padding-left: 18px;
  }
</style>
