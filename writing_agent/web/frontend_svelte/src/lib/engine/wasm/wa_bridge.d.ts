/* tslint:disable */
/* eslint-disable */

export class WasmEditor {
    free(): void;
    [Symbol.dispose](): void;
    checkpoint(): void;
    deleteBackward(): void;
    exportJson(): string;
    exportMarkdown(): string;
    find(query: string): any;
    getCursorPosition(): any;
    getStats(): any;
    importMarkdown(md: string): void;
    insertCode(lang: string, code: string): void;
    insertFigure(url: string, caption?: string | null): void;
    insertImage(url: string): void;
    insertLink(url: string, text: string): void;
    insertList(ordered: boolean): void;
    insertQuote(text: string): void;
    insertTable(rows: number, cols: number): void;
    insertText(text: string): void;
    layout(width: number): any;
    listIndent(): void;
    listOutdent(): void;
    loadJson(json: string): void;
    constructor();
    redo(): void;
    replace(query: string, replacement: string): number;
    setHeading(level: number): void;
    tableDeleteColumn(): void;
    tableDeleteRow(): void;
    tableInsertColumn(): void;
    tableInsertRow(): void;
    toggleBold(): void;
    toggleItalic(): void;
    toggleStrikethrough(): void;
    toggleUnderline(): void;
    undo(): void;
}

export function main(): void;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_wasmeditor_free: (a: number, b: number) => void;
    readonly wasmeditor_checkpoint: (a: number) => void;
    readonly wasmeditor_deleteBackward: (a: number) => void;
    readonly wasmeditor_exportJson: (a: number) => [number, number, number, number];
    readonly wasmeditor_exportMarkdown: (a: number) => [number, number];
    readonly wasmeditor_find: (a: number, b: number, c: number) => any;
    readonly wasmeditor_getCursorPosition: (a: number) => any;
    readonly wasmeditor_getStats: (a: number) => any;
    readonly wasmeditor_importMarkdown: (a: number, b: number, c: number) => [number, number];
    readonly wasmeditor_insertCode: (a: number, b: number, c: number, d: number, e: number) => void;
    readonly wasmeditor_insertFigure: (a: number, b: number, c: number, d: number, e: number) => void;
    readonly wasmeditor_insertImage: (a: number, b: number, c: number) => void;
    readonly wasmeditor_insertLink: (a: number, b: number, c: number, d: number, e: number) => void;
    readonly wasmeditor_insertList: (a: number, b: number) => void;
    readonly wasmeditor_insertQuote: (a: number, b: number, c: number) => void;
    readonly wasmeditor_insertTable: (a: number, b: number, c: number) => void;
    readonly wasmeditor_insertText: (a: number, b: number, c: number) => void;
    readonly wasmeditor_layout: (a: number, b: number) => [number, number, number];
    readonly wasmeditor_listIndent: (a: number) => void;
    readonly wasmeditor_listOutdent: (a: number) => void;
    readonly wasmeditor_loadJson: (a: number, b: number, c: number) => [number, number];
    readonly wasmeditor_new: () => number;
    readonly wasmeditor_redo: (a: number) => void;
    readonly wasmeditor_replace: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly wasmeditor_setHeading: (a: number, b: number) => void;
    readonly wasmeditor_tableDeleteColumn: (a: number) => void;
    readonly wasmeditor_tableDeleteRow: (a: number) => void;
    readonly wasmeditor_tableInsertColumn: (a: number) => void;
    readonly wasmeditor_tableInsertRow: (a: number) => void;
    readonly wasmeditor_toggleBold: (a: number) => void;
    readonly wasmeditor_toggleItalic: (a: number) => void;
    readonly wasmeditor_toggleStrikethrough: (a: number) => void;
    readonly wasmeditor_toggleUnderline: (a: number) => void;
    readonly wasmeditor_undo: (a: number) => void;
    readonly main: () => void;
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __wbindgen_exn_store: (a: number) => void;
    readonly __externref_table_alloc: () => number;
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
