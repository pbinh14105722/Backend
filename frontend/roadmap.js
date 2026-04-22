/**
 * Roadmap Builder — js/roadmap.js
 * Design system: Manask dark theme
 * All persistence via API (utils.fetchWithAuth)
 */

import * as utils from '../utils.js';
import { t, initI18n } from '../i18n.js';
import { showHintFloat } from './hint_float.js';

// ── API ENDPOINTS ──────────────────────────────────────────────────────────
const API = utils.URL_API;

const EP = {
    // Left sidebar — cùng endpoint với sidebar-nav ở home
    items:           () => `${API}/items`,

    // Roadmap list (right sidebar)
    roadmaps:        () => `${API}/roadmap`,
    roadmap:       (id) => `${API}/roadmap/${id}`,

    // Node CRUD inside a roadmap
    nodes:         (id) => `${API}/roadmap/${id}/node`,
    node:     (id, nid) => `${API}/roadmap/${id}/node/${nid}`,
};

// ── STATE ──────────────────────────────────────────────────────────────────
let ITEMS = [];          // items fetched from API (left sidebar source)

let nodes  = {};         // { nid: { x, y, item } }
let edges  = [];         // [ { from, to, fromPort, toPort, etype, style, label } ]
let nCnt   = 0;

let selNode      = null;
let connPortFirst = null; // { nid, port }
let activeEdgeIdx = null;

// Pan / Zoom
let panX = 0, panY = 0, zoom = 1;
let isPanning = false, panStart = { x: 0, y: 0 };

// Roadmap list
let roadmaps    = [];
let activeRmId  = null;

// Save debounce
let saveTimer = null;
const SAVE_DELAY = 800; // ms

// ── DOM REFS ───────────────────────────────────────────────────────────────
const cw  = document.getElementById('cw');
const ct  = document.getElementById('canvas-transform');
const cnv = document.getElementById('cnv');

// ── BOOT ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await initI18n();
    await utils.ensureUserId();
    setupEventListeners();
    setupMobileBar();
    setupOfflineBanner();
    setupResizer();
    await Promise.all([loadItems(), loadRoadmaps()]);
    setupMiniToolbar();

    showHintFloat({
        storageKey:   'manask_roadmap_hinted',
        title:        () => t('hints.roadmap_title'),
        steps: [
            () => t('hints.roadmap_step1'),
            () => t('hints.roadmap_step2'),
            () => t('hints.roadmap_step3'),
        ],
        dismissLabel: () => t('hints.dismiss'),
    });
});

function setupOfflineBanner() {
    const banner = document.getElementById('rm-offline-banner');
    if (!banner) return;
    const update = () => {
        banner.style.display = navigator.onLine ? 'none' : 'flex';
    };
    update();
    window.addEventListener('online',  update);
    window.addEventListener('offline', update);
}

// ═══════════════════════════════════════════════════════════════════════════
// LEFT SIDEBAR — reuses /items API + same HTML structure as sidebar_nav.js
//   Differences vs home sidebar:
//     • No modal-more (no CRUD)
//     • No SortableJS (drag goes to canvas instead)
//     • project-item-child & folder header are draggable to canvas
// ═══════════════════════════════════════════════════════════════════════════

async function loadItems() {
    const list = document.getElementById('rm-item-list');
    let loadError = false;
    try {
        const res = await utils.fetchWithAuth(EP.items());
        if (!res.ok) throw new Error('Failed to load items');
        ITEMS = await res.json();
        ITEMS.sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    } catch (err) {
        console.error('[Roadmap] loadItems:', err);
        ITEMS = [];
        loadError = true;
    }
    list.innerHTML = '';
    if (loadError) {
        list.innerHTML = `<li><div class="rm-load-error">
            <svg class="rm-load-error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span class="rm-load-error-text">Không tải được thành phần</span>
            <button class="rm-load-error-retry" data-retry="items">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/>
                </svg>Thử lại
            </button>
        </div></li>`;
        return;
    }
    if (!ITEMS.length) {
        list.innerHTML = `<li style="padding:20px 14px;text-align:center;font-size:12px;color:var(--text-tertiary)">
            ${t('roadmap.components_empty')}</li>`;
        return;
    }
    renderSidebarRecursive(null, list);
    applySearchFilter('');
}

/** Recursive render — mirrors sidebar_nav.js renderRecursive() */
function renderSidebarRecursive(parentId, container) {
    const children = ITEMS.filter(i => (i.parent_id ?? null) === parentId);
    children.forEach(item => {
        renderSidebarItem(item, container);
        if (item.type === 'FOLDER') {
            const sub = container.querySelector(`[data-id="${item.id}"] .list-wrapper`);
            if (sub) renderSidebarRecursive(item.id, sub);
        }
    });
}

/** renderItem() — same HTML as sidebar_nav.js but without .modal-more */
function renderSidebarItem(item, wrapper) {
    const color         = item.color || '#ffffff';
    const expandedClass = item.expanded ? 'is-expanded' : '';
    const showExpanded  = item.expanded ? 'block' : 'none';
    const showCollapsed = item.expanded ? 'none'  : 'block';

    let html = '';

    if (item.type === 'FOLDER') {
        html = `
        <li class="folder-item ${expandedClass}" data-id="${item.id}">
            <div class="item-header">
                <svg class="icon-collapsed" viewBox="0 0 24 24" style="display:${showCollapsed};">
                    <polyline points="8,5 16,12 8,19"/>
                </svg>
                <svg class="icon-expanded" viewBox="0 0 24 24" style="display:${showExpanded};">
                    <polyline points="5,8 12,16 19,8"/>
                </svg>
                <!-- drag zone: icon + label -->
                <div class="folder-drag-area" draggable="true" data-iid="${item.id}">
                    <svg class="folder-icon" viewBox="0 0 64 64">
                        <path d="M8 20 H22 L26 16 H44 Q50 16 50 22 V40 Q50 48 42 48 H16 Q8 48 8 40 Z"
                              fill="${color}"/>
                    </svg>
                    <p class="label">${escHtml(item.name)}</p>
                </div>
            </div>
            <div class="item-content">
                <ul class="list-wrapper"></ul>
            </div>
        </li>`;
    } else {
        // PROJECT or TASK
        html = `
        <li class="project-item-child" data-id="${item.id}" draggable="true" data-iid="${item.id}">
            <svg class="project-icon" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="${color}"/>
            </svg>
            <p>${escHtml(item.name)}</p>
        </li>`;
    }

    wrapper.insertAdjacentHTML('beforeend', html);
    attachSidebarEvents(wrapper.lastElementChild);
}

/** Attach expand/collapse + drag events — no CRUD */
function attachSidebarEvents(item) {
    if (item.classList.contains('folder-item')) {
        // Expand/collapse on chevrons or header (not drag zone)
        item.querySelector('.item-header').addEventListener('click', function (e) {
            if (e.target.closest('.folder-drag-area')) return; // let drag handle it
            toggleFolder(item);
        });
        item.querySelector('.icon-collapsed')?.addEventListener('click', e => {
            e.stopPropagation();
            toggleFolder(item);
        });
        item.querySelector('.icon-expanded')?.addEventListener('click', e => {
            e.stopPropagation();
            toggleFolder(item);
        });

        // Drag folder to canvas
        const dragArea = item.querySelector('.folder-drag-area');
        dragArea?.addEventListener('dragstart', e => {
            e.stopPropagation();
            e.dataTransfer.setData('iid', dragArea.dataset.iid);
            e.dataTransfer.effectAllowed = 'copy';
            attachDragGhost(e, dragArea);
        });
        // Click on drag area still toggles folder
        dragArea?.addEventListener('click', () => toggleFolder(item));
    }

    if (item.classList.contains('project-item-child')) {
        item.addEventListener('dragstart', e => {
            e.dataTransfer.setData('iid', item.dataset.iid);
            e.dataTransfer.effectAllowed = 'copy';
            attachDragGhost(e, item);
        });
    }
}

/** Tạo ghost có viền xanh cho desktop drag, dùng setDragImage thay native screenshot */
function attachDragGhost(e, sourceEl) {
    const ghost = buildTouchGhost(sourceEl);
    ghost.style.opacity = '1';
    ghost.style.top  = '-9999px';
    ghost.style.left = '-9999px';
    document.body.appendChild(ghost);
    e.dataTransfer.setDragImage(ghost, 40, 20);
    requestAnimationFrame(() => ghost.remove());
}

function toggleFolder(item) {
    const isExpanded = item.classList.toggle('is-expanded');
    item.querySelector('.icon-expanded').style.display = isExpanded ? 'block' : 'none';
    item.querySelector('.icon-collapsed').style.display = isExpanded ? 'none'  : 'block';
}

/** Filter sidebar items by search query (hide/show li elements) */
function applySearchFilter(q) {
    const list = document.getElementById('rm-item-list');
    q = q.toLowerCase().trim();
    if (!q) {
        list.querySelectorAll('li').forEach(li => li.style.display = '');
        return;
    }
    // Show only items whose name matches; always show parent folder if child matches
    const matchIds = new Set(
        ITEMS.filter(i => i.name.toLowerCase().includes(q)).map(i => i.id)
    );
    // Also include ancestor folders
    function addAncestors(id) {
        const item = ITEMS.find(i => i.id === id);
        if (!item || !item.parent_id) return;
        matchIds.add(item.parent_id);
        addAncestors(item.parent_id);
    }
    matchIds.forEach(id => addAncestors(id));

    // Remove previous "no results" message
    list.querySelectorAll('.rm-search-empty').forEach(el => el.remove());

    let anyVisible = false;
    list.querySelectorAll('li[data-id]').forEach(li => {
        const visible = matchIds.has(li.dataset.id);
        li.style.display = visible ? '' : 'none';
        if (visible) anyVisible = true;
    });

    if (!anyVisible) {
        const empty = document.createElement('li');
        empty.className = 'rm-search-empty';
        empty.style.cssText = 'padding:20px 14px;text-align:center;font-size:12px;color:var(--text-tertiary)';
        empty.textContent = t('roadmap.search_no_results');
        list.appendChild(empty);
    }

    // Expand matched folders
    list.querySelectorAll('.folder-item').forEach(fi => {
        if (matchIds.has(fi.dataset.id)) fi.classList.add('is-expanded');
    });
}

// Search input
document.getElementById('sb-search').addEventListener('input', e => {
    applySearchFilter(e.target.value);
});

// ═══════════════════════════════════════════════════════════════════════════
// RIGHT SIDEBAR — ROADMAP LIST
// ═══════════════════════════════════════════════════════════════════════════

async function loadRoadmaps() {
    let loadError = false;
    try {
        const res = await utils.fetchWithAuth(EP.roadmaps());
        if (!res.ok) throw new Error('Failed to load roadmaps');
        roadmaps = await res.json();
    } catch (err) {
        console.error('[Roadmap] loadRoadmaps:', err);
        roadmaps = [];
        loadError = true;
    }

    if (loadError) {
        const body = document.getElementById('sb-right-body');
        body.innerHTML = `<div class="rm-load-error">
            <svg class="rm-load-error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span class="rm-load-error-text">Không tải được roadmaps</span>
            <button class="rm-load-error-retry" data-retry="roadmaps">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.51"/>
                </svg>Thử lại
            </button>
        </div>`;
        return;
    }

    renderRoadmapList();

    // Auto-select first
    if (roadmaps.length && !activeRmId) {
        await switchRoadmap(roadmaps[0].id);
    } else {
        updateEmpty();
    }
}

function renderRoadmapList() {
    const body = document.getElementById('sb-right-body');
    body.innerHTML = '';

    if (!roadmaps.length) {
        body.innerHTML = `<div class="rm-list-empty">${t('roadmap.roadmaps_empty')}</div>`;
        return;
    }

    roadmaps.forEach(rm => {
        const el = document.createElement('div');
        el.className = 'rm-item' + (rm.id === activeRmId ? ' active' : '');
        el.dataset.rmid = rm.id;

        const nodeCount = Object.keys(rm.nodes || {}).length;
        const edgeCount = (rm.edges || []).length;

        el.innerHTML = `
            <div class="rm-item-head">
                <span class="rm-color-dot" style="background:#6366f1"></span>
                <span class="rm-title" title="${escHtml(rm.name)}">${escHtml(rm.name)}</span>
                <div class="rm-item-btns">
                    <button class="rm-btn" data-action="rename" title="Đổi tên">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                             stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="rm-btn danger" data-action="delete" title="Xóa">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                             stroke-linecap="round">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="rm-meta">
                <span class="rm-meta-item">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="7" height="7" rx="1"/>
                        <rect x="14" y="3" width="7" height="7" rx="1"/>
                        <rect x="3" y="14" width="7" height="7" rx="1"/>
                        <rect x="14" y="14" width="7" height="7" rx="1"/>
                    </svg>
                    ${nodeCount} node
                </span>
                <span class="rm-meta-item">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="5" y1="12" x2="19" y2="12"/>
                        <polyline points="12 5 19 12 12 19"/>
                    </svg>
                    ${edgeCount} kết nối
                </span>
            </div>`;

        el.addEventListener('click', async e => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            if (action === 'rename') { e.stopPropagation(); renameRm(rm.id); return; }
            if (action === 'delete') { e.stopPropagation(); deleteRm(rm.id); return; }
            if (e.target.classList.contains('rm-title-input')) return;
            await switchRoadmap(rm.id);
        });

        body.appendChild(el);
    });
}

async function newRoadmap() {
    const name = 'Roadmap ' + (roadmaps.length + 1);
    try {
        setSaveState('saving');
        const res = await utils.fetchWithAuth(EP.roadmaps(), {
            method: 'POST',
            body: JSON.stringify({ name, nodes: {}, edges: [], nCnt: 0, panX: 0, panY: 0, zoom: 1 })
        });
        if (!res.ok) throw new Error('Create failed');
        const rm = await res.json();
        roadmaps.push(rm);
        setSaveState('saved');
        renderRoadmapList();
        await switchRoadmap(rm.id);
        utils.showSuccess(t('roadmap.msg_created'));
    } catch (err) {
        console.error('[Roadmap] newRoadmap:', err);
        setSaveState('error');
    }
}

async function switchRoadmap(id) {
    if (id === activeRmId) return;

    // Flush pending save for current roadmap
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; await flushSave(); }

    activeRmId = id;
    await loadActiveRoadmap();
    renderRoadmapList();
}

async function deleteRm(id) {
    if (roadmaps.length <= 1) {
        utils.showWarning(t('roadmap.rm_need_one'));
        return;
    }
    try {
        setSaveState('saving');
        const res = await utils.fetchWithAuth(
            EP.roadmap(id),
            { method: 'DELETE' },
            { enableQueue: true },
            utils.generateId(), 1
        );
        if (!res.ok) throw new Error('Delete failed');
        roadmaps = roadmaps.filter(r => r.id !== id);
        setSaveState('saved');
        utils.showSuccess(t('roadmap.msg_deleted'));
        if (activeRmId === id) {
            activeRmId = null;
            await switchRoadmap(roadmaps[0].id);
        } else {
            renderRoadmapList();
        }
    } catch (err) {
        console.error('[Roadmap] deleteRm:', err);
        setSaveState('error');
    }
}

function renameRm(id) {
    const el = document.querySelector(`.rm-item[data-rmid="${id}"]`);
    if (!el) return;
    const titleEl = el.querySelector('.rm-title');
    const rm = roadmaps.find(r => r.id === id);
    if (!rm || !titleEl) return;

    const inp = document.createElement('input');
    inp.className = 'rm-title-input';
    inp.value = rm.name;
    titleEl.replaceWith(inp);
    inp.focus(); inp.select();

    async function done() {
        const val = inp.value.trim() || rm.name;
        inp.removeEventListener('blur', done);
        rm.name = val;
        const span = document.createElement('span');
        span.className = 'rm-title';
        span.title = val;
        span.textContent = val;
        inp.replaceWith(span);

        try {
            setSaveState('saving');
            const res = await utils.fetchWithAuth(
                EP.roadmap(id),
                { method: 'PATCH', body: JSON.stringify({ name: val }) },
                { enableQueue: true, optimisticData: { name: val } },
                utils.generateId(), 1
            );
            if (!res.ok) throw new Error('Rename failed');
            setSaveState('saved');
            utils.showSuccess(t('roadmap.msg_renamed'));
        } catch (err) {
            console.error('[Roadmap] renameRm:', err);
            setSaveState('error');
        }
    }

    inp.addEventListener('blur', done);
    inp.addEventListener('keydown', e => {
        if (e.key === 'Enter') { inp.blur(); }
        if (e.key === 'Escape') { inp.value = rm.name; inp.blur(); }
    });
}

// ── Wiring new roadmap button ──────────────────────────────────────────────
document.getElementById('btn-new-rm').addEventListener('click', newRoadmap);

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — LOAD / SAVE
// ═══════════════════════════════════════════════════════════════════════════

async function loadActiveRoadmap() {
    if (!activeRmId) return;
    try {
        const res = await utils.fetchWithAuth(EP.roadmap(activeRmId));
        if (!res.ok) throw new Error('Load roadmap failed');
        const data = await res.json();

        console.log('[Roadmap] Loaded roadmap data:', data);

        nodes = data.nodes  || {};
        edges = data.edges  || [];
        nCnt  = data.nCnt   || 0;
        panX  = data.panX   || 0;
        panY  = data.panY   || 0;
        zoom  = data.zoom   || 1;
    } catch (err) {
        console.error('[Roadmap] loadActiveRoadmap:', err);
        nodes = {}; edges = []; nCnt = 0; panX = 0; panY = 0; zoom = 1;
    }

    // Rebuild DOM
    cnv.innerHTML = '';
    Object.entries(nodes).forEach(([nid, nd]) => rebuildNode(nid, nd));
    renderEdges();
    updateTransform();
    updateEmpty();
    selNode = null;
    connPortFirst = null;
}

/** Debounced: schedule an API PATCH for the active roadmap */
function saveState() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flushSave, SAVE_DELAY);
    setSaveState('saving');
}

async function flushSave() {
    if (!activeRmId) return;
    // Sync current roadmap object in list
    const rm = roadmaps.find(r => r.id === activeRmId);
    if (rm) {
        rm.nodes = JSON.parse(JSON.stringify(nodes));
        rm.edges = JSON.parse(JSON.stringify(edges));
        rm.nCnt  = nCnt;
        rm.panX  = panX; rm.panY = panY; rm.zoom = zoom;
    }
    try {
        const res = await utils.fetchWithAuth(EP.roadmap(activeRmId), {
            method: 'PATCH',
            body: JSON.stringify({ nodes, edges, nCnt, panX, panY, zoom })
        });
        if (!res.ok) throw new Error('Save failed');
        setSaveState('saved');
        // Refresh count badges without full re-render
        renderRoadmapList();
    } catch (err) {
        console.error('[Roadmap] flushSave:', err);
        setSaveState('error');
    }
}

/** Visual indicator: 'saving' | 'saved' | 'error' | '' */
function setSaveState(state) {
    const dot   = document.getElementById('rm-save-dot');
    const label = document.getElementById('rm-save-label');
    dot.className   = 'rm-save-dot' + (state ? ' ' + state : '');
    label.textContent = state === 'saving' ? t('roadmap.saving')
                      : state === 'saved'  ? t('roadmap.saved')
                      : state === 'error'  ? t('roadmap.save_error')
                      : '';
    if (state === 'saved') setTimeout(() => {
        if (dot.classList.contains('saved')) { dot.className = 'rm-save-dot'; label.textContent = ''; }
    }, 2000);
}

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — PAN / ZOOM
// ═══════════════════════════════════════════════════════════════════════════

function updateTransform() {
    ct.style.transform = `translate(${panX}px,${panY}px) scale(${zoom})`;
    document.getElementById('zoom-badge').textContent = Math.round(zoom * 100) + '%';
}

function zoomReset() { zoom = 1; panX = 0; panY = 0; updateTransform(); saveState(); }

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — NODES
// ═══════════════════════════════════════════════════════════════════════════

function addNode(itemId, x, y) {
    const item = ITEMS.find(i => i.id === itemId);
    if (!item) return;
    const nid = 'n' + (++nCnt);
    nodes[nid] = { x, y, item };
    const el = createNodeEl(nid, item);
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
    cnv.appendChild(el);
    updateEmpty();
    selectNd(nid);
    saveState();
}

function rebuildNode(nid, nd) {
    const el = createNodeEl(nid, nd.item);
    el.style.left = nd.x + 'px';
    el.style.top  = nd.y + 'px';
    cnv.appendChild(el);
}

function createNodeEl(nid, item) {
    const el = document.createElement('div');
    el.id = 'nd-' + nid;
    el.className = 'nd nd-new';
    setTimeout(() => el.classList.remove('nd-new'), 400);

    const typeLabel = { FOLDER: 'Folder', PROJECT: 'Project', TASK: 'Task' }[item.type] || item.type;

    // Icon style
    let icoStyle = '';
    if (item.type === 'TASK') {
        icoStyle = `border-radius:50%;border:2px solid ${item.color || '#a1a1aa'};background:transparent`;
    } else if (item.type === 'FOLDER') {
        icoStyle = `border-radius:4px;background:${item.color || '#6366f1'}`;
    } else {
        icoStyle = `border-radius:3px;background:${item.color || '#6366f1'}`;
    }

    // Parent name - lấy trực tiếp từ data thay vì tìm trong folder tree
    const parentName = item.parent_name || null;

    el.innerHTML = `
        <div class="nd-hdr">
            <div class="nd-ico" style="${icoStyle}"></div>
            <span class="nd-lbl">${escHtml(typeLabel)}</span>
        </div>
        <div class="nd-name">${escHtml(item.name)}</div>
        ${parentName ? `<div class="nd-sub">↳ ${escHtml(parentName)}</div>` : ''}
        <button class="nd-del" aria-label="Xóa node">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                 stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6"  y1="6" x2="18" y2="18"/>
            </svg>
        </button>
        <div class="ports">
            <div class="port" data-p="top"    data-nid="${nid}"></div>
            <div class="port" data-p="bottom" data-nid="${nid}"></div>
            <div class="port" data-p="left"   data-nid="${nid}"></div>
            <div class="port" data-p="right"  data-nid="${nid}"></div>
        </div>`;

    // Delete button
    el.querySelector('.nd-del').addEventListener('click', e => {
        e.stopPropagation();
        delNode(nid);
    });

    // Port clicks
    el.querySelectorAll('.port').forEach(port => {
        port.addEventListener('click', e => {
            e.stopPropagation();
            handlePortClick(nid, port.dataset.p, port);
        });
    });

    // Drag (mouse)
    el.addEventListener('mousedown', e => {
        if (e.target.classList.contains('port') || e.target.closest('.nd-del')) return;
        e.stopPropagation();
        selectNd(nid);
        e.preventDefault();
        const startX = e.clientX / zoom - nodes[nid].x;
        const startY = e.clientY / zoom - nodes[nid].y;

        function onMove(mv) {
            nodes[nid].x = mv.clientX / zoom - startX;
            nodes[nid].y = mv.clientY / zoom - startY;
            el.style.left = nodes[nid].x + 'px';
            el.style.top  = nodes[nid].y + 'px';
            renderEdges();
        }
        function onUp() {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            saveState();
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

    // Drag (touch) — long-press 250ms then drag node
    (function() {
        const HOLD_MS = 250;
        let holdTimer = null;
        let touchMoving = false;
        let startTX = 0, startTY = 0;
        let startNX = 0, startNY = 0;
        let activeTouchId = null;

        function cancelHold() {
            if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
        }

        el.addEventListener('touchstart', e => {
            if (e.target.classList.contains('port') || e.target.closest('.nd-del')) return;
            e.stopPropagation();
            const t = e.touches[0];
            activeTouchId = t.identifier;
            startTX = t.clientX; startTY = t.clientY;
            startNX = nodes[nid].x; startNY = nodes[nid].y;
            touchMoving = false;

            holdTimer = setTimeout(() => {
                holdTimer = null;
                touchMoving = true;
                selectNd(nid);
                el.classList.add('touch-dragging');
                if (navigator.vibrate) navigator.vibrate(30);
            }, HOLD_MS);
        }, { passive: true });

        el.addEventListener('touchmove', e => {
            const t = Array.from(e.touches).find(t => t.identifier === activeTouchId);
            if (!t) return;

            // Cancel hold if moved too early
            if (holdTimer) {
                const dx = t.clientX - startTX, dy = t.clientY - startTY;
                if (Math.hypot(dx, dy) > 6) cancelHold();
                return;
            }

            if (!touchMoving) return;
            e.preventDefault();
            e.stopPropagation();

            // Position = (touch - canvas offset - pan) / zoom, offset by grab point
            const rect = cw.getBoundingClientRect();
            const grabOffX = (startTX - rect.left - panX) / zoom - startNX;
            const grabOffY = (startTY - rect.top  - panY) / zoom - startNY;
            nodes[nid].x = (t.clientX - rect.left - panX) / zoom - grabOffX;
            nodes[nid].y = (t.clientY - rect.top  - panY) / zoom - grabOffY;
            el.style.left = nodes[nid].x + 'px';
            el.style.top  = nodes[nid].y + 'px';
            renderEdges();
        }, { passive: false });

        el.addEventListener('touchend', () => {
            cancelHold();
            el.classList.remove('touch-dragging');
            if (touchMoving) saveState();
            touchMoving = false;
            activeTouchId = null;
        }, { passive: true });

        el.addEventListener('touchcancel', () => {
            cancelHold();
            el.classList.remove('touch-dragging');
            touchMoving = false;
            activeTouchId = null;
        }, { passive: true });
    })();

    return el;
}

function selectNd(nid) {
    if (selNode) ndEl(selNode)?.classList.remove('sel');
    selNode = nid;
    if (nid) ndEl(nid)?.classList.add('sel');
}

function delNode(nid) {
    ndEl(nid)?.remove();
    delete nodes[nid];
    edges = edges.filter(e => e.from !== nid && e.to !== nid);
    if (selNode === nid) selNode = null;
    renderEdges();
    updateEmpty();
    saveState();
}

function updateEmpty() {
    document.getElementById('empty-state').style.display =
        Object.keys(nodes).length ? 'none' : '';
}

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — PORT CONNECTION
// ═══════════════════════════════════════════════════════════════════════════

function handlePortClick(nid, portName, portEl) {
    if (!connPortFirst) {
        connPortFirst = { nid, port: portName };
        portEl.classList.add('port-pending');
        ndEl(nid)?.classList.add('port-active');
        setHint('Nhấn vào cổng của node đích để nối · Esc huỷ');
    } else {
        if (connPortFirst.nid === nid) {
            connPortFirst = null; clearPendingPorts(); setPrev('');
            setHint('Kéo thả để thêm · Click nền để di chuyển · Ctrl + Scroll để zoom');
            return;
        }
        const dup = edges.find(e =>
            e.from === connPortFirst.nid && e.to === nid &&
            e.fromPort === connPortFirst.port && e.toPort === portName
        );
        if (!dup) {
            edges.push({
                from: connPortFirst.nid, to: nid,
                fromPort: connPortFirst.port, toPort: portName,
                etype: 'one', style: 'solid', label: ''
            });
        }
        connPortFirst = null; clearPendingPorts(); setPrev('');
        renderEdges(); saveState();
        setHint('Kéo thả để thêm · Click nền để di chuyển · Ctrl + Scroll để zoom');
    }
}

function clearPendingPorts() {
    document.querySelectorAll('.port-pending').forEach(p => p.classList.remove('port-pending'));
    document.querySelectorAll('.port-active').forEach(n => n.classList.remove('port-active'));
}

// Preview wire
document.addEventListener('mousemove', e => {
    if (!connPortFirst) return;
    const rect = cw.getBoundingClientRect();
    const mx = (e.clientX - rect.left - panX) / zoom;
    const my = (e.clientY - rect.top  - panY) / zoom;
    const A  = portXY(connPortFirst.nid, connPortFirst.port);
    setPrev(`M${A.x},${A.y} Q${(A.x + mx) / 2},${A.y} ${mx},${my}`);
});

function setPrev(d) { document.getElementById('prev-path').setAttribute('d', d); }
function setHint(msg) { document.getElementById('hint-bar').textContent = msg; }

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — EDGES RENDER
// ═══════════════════════════════════════════════════════════════════════════

function ensureMarkers() {
    const defs = document.getElementById('svg-defs');
    if (defs.innerHTML) return;
    const mk = [
        { id: 'mk-default', color: '#a1a1aa' },
        { id: 'mk-green',   color: '#22c55e' },
        { id: 'mk-purple',  color: '#8b5cf6' },
        { id: 'mk-blue',    color: '#6366f1' },
        { id: 'mk-amber',   color: '#f59e0b' },
    ];
    mk.forEach(({ id, color }) => {
        defs.innerHTML += `<marker id="${id}" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 Z" fill="${color}"/>
        </marker>`;
    });
}

function getMarker(color) {
    if (!color) return 'mk-default';
    const c = color.toLowerCase();
    if (c.includes('22c5') || c.includes('1da8')) return 'mk-green';
    if (c.includes('8b5c') || c.includes('6b4d') || c.includes('4f52')) return 'mk-purple';
    if (c.includes('6366') || c.includes('4f8e')) return 'mk-blue';
    if (c.includes('f59e') || c.includes('f794')) return 'mk-amber';
    return 'mk-default';
}

function getDash(style) {
    if (style === 'dashed') return '8,5';
    if (style === 'dotted') return '2,4';
    return null;
}

function renderEdges() {
    ensureMarkers();
    const g = document.getElementById('edge-g');
    while (g.firstChild) g.removeChild(g.firstChild);

    edges.forEach((e, i) => {
        if (!nodes[e.from] || !nodes[e.to]) return;
        let fp = e.fromPort, tp = e.toPort;
        if (!fp || !tp) { const bp = bestPorts(e.from, e.to); fp = bp.fp; tp = bp.tp; }
        const A = portXY(e.from, fp), B = portXY(e.to, tp);
        const d   = cubicD(A, fp, B, tp);
        const col = nodes[e.from].item?.color || '#a1a1aa';
        const mk  = getMarker(col);
        const opacity = e.style === 'faded' ? 0.2 : 0.8;
        const da  = getDash(e.style);

        // Hit area
        const hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        hit.setAttribute('d', d);
        hit.setAttribute('stroke', 'transparent');
        hit.setAttribute('stroke-width', '14');
        hit.setAttribute('fill', 'none');
        hit.style.pointerEvents = 'stroke';
        hit.style.cursor = 'pointer';
        hit.addEventListener('click', ev => { ev.stopPropagation(); openEdgePopup(ev, i); });

        // Visual path
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('stroke', col);
        path.setAttribute('stroke-width', '1.8');
        path.setAttribute('fill', 'none');
        path.setAttribute('opacity', String(opacity));
        path.style.pointerEvents = 'none';
        if (da)           path.setAttribute('stroke-dasharray', da);
        if (e.etype === 'two') path.setAttribute('marker-start', `url(#${mk})`);
        if (e.etype === 'one' || e.etype === 'two') path.setAttribute('marker-end', `url(#${mk})`);

        g.appendChild(hit);
        g.appendChild(path);

        // Label
        if (e.label) {
            const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
            const tw = e.label.length * 6.5 + 12;
            const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            bg.setAttribute('x', String(mx - tw / 2)); bg.setAttribute('y', String(my - 15));
            bg.setAttribute('width', String(tw)); bg.setAttribute('height', '14');
            bg.setAttribute('rx', '4'); bg.setAttribute('fill', '#1a1a20'); bg.setAttribute('opacity', '0.9');
            bg.style.pointerEvents = 'none';

            const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            lbl.setAttribute('x', String(mx)); lbl.setAttribute('y', String(my - 4));
            lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('font-size', '10');
            lbl.setAttribute('fill', col); lbl.setAttribute('opacity', '0.9');
            lbl.setAttribute('font-family', 'DM Sans, sans-serif');
            lbl.style.pointerEvents = 'none';
            lbl.textContent = e.label;

            g.appendChild(bg); g.appendChild(lbl);
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — GEOMETRY
// ═══════════════════════════════════════════════════════════════════════════

function ndEl(nid)  { return document.getElementById('nd-' + nid); }

function ndBox(nid) {
    const n = nodes[nid], el = ndEl(nid);
    return { x: n.x, y: n.y, w: el ? el.offsetWidth : 160, h: el ? el.offsetHeight : 72 };
}

function portXY(nid, p) {
    const b = ndBox(nid);
    const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
    if (p === 'top')    return { x: cx, y: b.y };
    if (p === 'bottom') return { x: cx, y: b.y + b.h };
    if (p === 'left')   return { x: b.x, y: cy };
    if (p === 'right')  return { x: b.x + b.w, y: cy };
    return { x: cx, y: cy };
}

function cubicD(A, fp, B, tp) {
    const d = 70;
    const c1 = { x: fp === 'right' ? A.x + d : fp === 'left' ? A.x - d : A.x,
                 y: fp === 'bottom' ? A.y + d : fp === 'top' ? A.y - d : A.y };
    const c2 = { x: tp === 'right' ? B.x + d : tp === 'left' ? B.x - d : B.x,
                 y: tp === 'bottom' ? B.y + d : tp === 'top' ? B.y - d : B.y };
    return `M${A.x},${A.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${B.x},${B.y}`;
}

function bestPorts(from, to) {
    const f = ndBox(from), t = ndBox(to);
    const dx = (t.x + t.w / 2) - (f.x + f.w / 2);
    const dy = (t.y + t.h / 2) - (f.y + f.h / 2);
    if (Math.abs(dy) >= Math.abs(dx))
        return { fp: dy > 0 ? 'bottom' : 'top', tp: dy > 0 ? 'top' : 'bottom' };
    return { fp: dx > 0 ? 'right' : 'left', tp: dx > 0 ? 'left' : 'right' };
}

// ═══════════════════════════════════════════════════════════════════════════
// CANVAS — EDGE POPUP
// ═══════════════════════════════════════════════════════════════════════════

function openEdgePopup(ev, i) {
    activeEdgeIdx = i;
    const e = edges[i];
    ['none','one','two'].forEach(v => document.getElementById('epa-' + v)?.classList.toggle('on', e.etype === v));
    ['solid','dashed','dotted','faded'].forEach(v => document.getElementById('eps-' + v)?.classList.toggle('on', e.style === v));
    document.getElementById('ep-label-input').value = e.label || '';

    const popup = document.getElementById('edge-popup');
    popup.style.display = 'block';
    let left = ev.clientX + 12, top = ev.clientY - 12;
    if (left + 250 > window.innerWidth)  left = ev.clientX - 260;
    if (top + 220  > window.innerHeight) top  = window.innerHeight - 230;
    popup.style.left = left + 'px';
    popup.style.top  = top  + 'px';
}

function closeEdgePopup() {
    document.getElementById('edge-popup').style.display = 'none';
    activeEdgeIdx = null;
}

document.getElementById('ep-close').addEventListener('click', closeEdgePopup);

document.getElementById('ep-del').addEventListener('click', () => {
    if (activeEdgeIdx == null) return;
    edges.splice(activeEdgeIdx, 1);
    closeEdgePopup(); renderEdges(); saveState();
});

document.getElementById('ep-label-input').addEventListener('input', e => {
    if (activeEdgeIdx == null) return;
    edges[activeEdgeIdx].label = e.target.value;
    renderEdges(); saveState();
});

['none','one','two'].forEach(v => {
    document.getElementById('epa-' + v)?.addEventListener('click', () => {
        if (activeEdgeIdx == null) return;
        edges[activeEdgeIdx].etype = v;
        ['none','one','two'].forEach(x => document.getElementById('epa-' + x)?.classList.toggle('on', x === v));
        renderEdges(); saveState();
    });
});

['solid','dashed','dotted','faded'].forEach(v => {
    document.getElementById('eps-' + v)?.addEventListener('click', () => {
        if (activeEdgeIdx == null) return;
        edges[activeEdgeIdx].style = v;
        ['solid','dashed','dotted','faded'].forEach(x => document.getElementById('eps-' + x)?.classList.toggle('on', x === v));
        renderEdges(); saveState();
    });
});

// ═══════════════════════════════════════════════════════════════════════════
// EVENT LISTENERS (canvas pan/zoom/drop/keyboard)
// ═══════════════════════════════════════════════════════════════════════════

function setupEventListeners() {
    // Retry buttons for load errors (event delegation)
    document.addEventListener('click', e => {
        const btn = e.target.closest('[data-retry]');
        if (!btn) return;
        if (btn.dataset.retry === 'items') loadItems();
        if (btn.dataset.retry === 'roadmaps') loadRoadmaps();
    });

    // Ctrl+Scroll zoom
    cw.addEventListener('wheel', e => {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const rect = cw.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const delta = e.deltaY > 0 ? 0.96 : 1.04;
        const newZoom = Math.max(0.15, Math.min(4, zoom * delta));
        panX = mx - (mx - panX) * (newZoom / zoom);
        panY = my - (my - panY) * (newZoom / zoom);
        zoom = newZoom;
        updateTransform(); saveState();
    }, { passive: false });

    // Pan on canvas background
    cw.addEventListener('mousedown', e => {
        // Bỏ qua synthetic mouse events do trình duyệt mobile tạo ra sau touch events
        if (e.sourceCapabilities?.firesTouchEvents) return;
        const bg = e.target === cw || e.target.id === 'cnv' ||
                   e.target.id === 'edge-svg' || e.target.id === 'canvas-transform' ||
                   e.target.closest('#edge-svg');
        if (!bg) return;
        isPanning = true;
        panStart = { x: e.clientX - panX, y: e.clientY - panY };
        cw.classList.add('panning');
    });

    document.addEventListener('mousemove', e => {
        if (!isPanning) return;
        panX = e.clientX - panStart.x;
        panY = e.clientY - panStart.y;
        updateTransform();
    });

    document.addEventListener('mouseup', () => {
        if (isPanning) {
            isPanning = false;
            cw.classList.remove('panning');
            saveState();
        }
    });

    // Click canvas → deselect / cancel connect
    cw.addEventListener('click', e => {
        if (e.target === cw || e.target.id === 'cnv' || e.target.id === 'canvas-transform') {
            selectNd(null);
            connPortFirst = null;
            clearPendingPorts(); setPrev('');
        }
        closeEdgePopup();
    });

    // Drop from left sidebar
    cw.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        cw.classList.add('drag-over');
    });

    cw.addEventListener('dragleave', () => cw.classList.remove('drag-over'));

    cw.addEventListener('drop', e => {
        e.preventDefault();
        cw.classList.remove('drag-over');
        const iid = e.dataTransfer.getData('iid');
        if (!iid) return;
        const r  = cw.getBoundingClientRect();
        const cx = (e.clientX - r.left - panX) / zoom;
        const cy = (e.clientY - r.top  - panY) / zoom;
        addNode(iid, cx - 80, cy - 36);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            connPortFirst = null; clearPendingPorts(); setPrev('');
            closeEdgePopup();
        }
        if ((e.key === 'Delete' || e.key === 'Backspace') &&
            selNode && document.activeElement.tagName !== 'INPUT') {
            delNode(selNode);
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
// MINI TOOLBAR
// ═══════════════════════════════════════════════════════════════════════════

function setupMiniToolbar() {
document.getElementById('mt-zoom-reset').addEventListener('click', zoomReset);
    document.getElementById('mt-clear').addEventListener('click', clearAll);
}

// ═══════════════════════════════════════════════════════════════════════════
// RESIZER — drag handle between #sb-right and #sb-left inside #sb-combined
// ═══════════════════════════════════════════════════════════════════════════

function setupResizer() {
    const resizer  = document.getElementById('rm-resizer');
    const sbRight  = document.getElementById('sb-right');
    const sbLeft   = document.getElementById('sb-left');
    const combined = document.getElementById('sb-combined');
    if (!resizer || !sbRight || !sbLeft || !combined) return;

    let dragging = false;
    let startY   = 0;
    let startTopFlex = 0;
    let startBotFlex = 0;

    resizer.addEventListener('mousedown', e => {
        e.preventDefault();
        dragging = true;
        startY = e.clientY;
        const totalH = combined.clientHeight - resizer.offsetHeight;
        startTopFlex = sbRight.getBoundingClientRect().height / totalH;
        startBotFlex = sbLeft.getBoundingClientRect().height  / totalH;
        resizer.classList.add('dragging');
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const totalH = combined.clientHeight - resizer.offsetHeight;
        const delta  = e.clientY - startY;
        const ratio  = delta / totalH;
        const newTop = Math.max(0.15, Math.min(0.85, startTopFlex + ratio));
        const newBot = 1 - newTop;
        sbRight.style.flex = newTop;
        sbLeft.style.flex  = newBot;
    });

    document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        resizer.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });
}

function clearAll() {
    if (!confirm(t('roadmap.clear_confirm'))) return;
    cnv.innerHTML = '';
    nodes = {}; edges = []; selNode = null; nCnt = 0;
    connPortFirst = null; clearPendingPorts(); setPrev('');
    renderEdges(); updateEmpty(); saveState();
}

// ═══════════════════════════════════════════════════════════════════════════
// MOBILE BAR
// ═══════════════════════════════════════════════════════════════════════════

function setupMobileBar() {
    const btnLeft  = document.getElementById('mob-btn-left');
    const btnRight = document.getElementById('mob-btn-right');
    const sbLeft   = document.getElementById('sb-left');
    const sbRight  = document.getElementById('sb-right');

    if (!btnLeft) return; // not in mobile context

    btnLeft.addEventListener('click',  () => toggleMobSidebar('left'));
    btnRight.addEventListener('click', () => toggleMobSidebar('right'));

    // Close sidebars when user taps directly on the canvas area
    // BUG FIX #1: nhận event để kiểm tra target — không đóng sidebar nếu người dùng
    // đang chạm VÀO sidebar (họ có thể đang bắt đầu long-press drag)
    document.getElementById('rm-main')?.addEventListener('touchstart', (e) => {
        const sbLeft  = document.getElementById('sb-left');
        const sbRight = document.getElementById('sb-right');
        if (sbLeft?.classList.contains('mob-open') && sbLeft.contains(e.target)) return;
        if (sbRight?.classList.contains('mob-open') && sbRight.contains(e.target)) return;
        if (sbLeft?.classList.contains('mob-open') || sbRight?.classList.contains('mob-open')) {
            closeAllMobSidebars();
        }
    }, { passive: true });

    // Touch-drag: drag items from left sidebar onto canvas
    setupTouchDrag();

    // ── Single-finger pan + two-finger pinch zoom on canvas ──
    let lastDist   = null;
    let panTouch   = null; // { id, startX, startY, lastX, lastY }
    let isPanTouch = false;

    cw.addEventListener('touchstart', e => {
        if (e.touches.length === 1) {
            // Only pan if touch started on background (not a node/port)
            const bg = e.target === cw || e.target.id === 'cnv' ||
                       e.target.id === 'canvas-transform' || e.target.id === 'edge-g' ||
                       e.target.closest('#edge-svg');
            if (bg) {
                const t = e.touches[0];
                panTouch = { id: t.identifier, lastX: t.clientX, lastY: t.clientY };
                isPanTouch = true;
            }
        } else if (e.touches.length === 2) {
            isPanTouch = false;
            panTouch = null;
            lastDist = getTouchDist(e.touches);
        }
    }, { passive: true });

    cw.addEventListener('touchmove', e => {
        if (e.touches.length === 2) {
            // Pinch zoom
            e.preventDefault();
            const d = getTouchDist(e.touches);
            if (lastDist) {
                const delta   = d / lastDist;
                const rect    = cw.getBoundingClientRect();
                const mid     = getTouchMid(e.touches, rect);
                const newZoom = Math.max(0.15, Math.min(4, zoom * delta));
                panX = mid.x - (mid.x - panX) * (newZoom / zoom);
                panY = mid.y - (mid.y - panY) * (newZoom / zoom);
                zoom = newZoom;
                updateTransform();
            }
            lastDist = d;
        } else if (e.touches.length === 1 && isPanTouch && panTouch) {
            // Single-finger pan
            e.preventDefault();
            const t = Array.from(e.touches).find(t => t.identifier === panTouch.id);
            if (!t) return;
            panX += t.clientX - panTouch.lastX;
            panY += t.clientY - panTouch.lastY;
            panTouch.lastX = t.clientX;
            panTouch.lastY = t.clientY;
            updateTransform();
        }
    }, { passive: false });

    cw.addEventListener('touchend', e => {
        if (e.touches.length < 2) lastDist = null;
        if (e.touches.length === 0) { isPanTouch = false; panTouch = null; }
        saveState();
    });

}

function toggleMobSidebar(side) {
    const sbLeft   = document.getElementById('sb-left');
    const sbRight  = document.getElementById('sb-right');
    const btnLeft  = document.getElementById('mob-btn-left');
    const btnRight = document.getElementById('mob-btn-right');

    if (side === 'left') {
        const opening = !sbLeft.classList.contains('mob-open');
        sbLeft.classList.toggle('mob-open', opening);
        sbRight.classList.remove('mob-open');
        btnLeft.classList.toggle('active', opening);
        btnRight.classList.remove('active');
        toggleBackdrop(opening);
    } else {
        const opening = !sbRight.classList.contains('mob-open');
        sbRight.classList.toggle('mob-open', opening);
        sbLeft.classList.remove('mob-open');
        btnRight.classList.toggle('active', opening);
        btnLeft.classList.remove('active');
        toggleBackdrop(opening);
    }
}

function toggleBackdrop(_show) {
    // Backdrop removed — sidebars close via tap-outside on #rm-main instead
}

function closeAllMobSidebars() {
    document.getElementById('sb-left')?.classList.remove('mob-open');
    document.getElementById('sb-right')?.classList.remove('mob-open');
    document.getElementById('mob-btn-left')?.classList.remove('active');
    document.getElementById('mob-btn-right')?.classList.remove('active');
}

function getTouchDist(ts) {
    return Math.hypot(ts[0].clientX - ts[1].clientX, ts[0].clientY - ts[1].clientY);
}

function getTouchMid(ts, rect) {
    return {
        x: ((ts[0].clientX + ts[1].clientX) / 2) - rect.left,
        y: ((ts[0].clientY + ts[1].clientY) / 2) - rect.top
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// TOUCH DRAG — drag items from sidebar onto canvas (mobile)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Call once at setup. Uses a MutationObserver so items rendered later
 * (after API load) also get touch drag attached automatically.
 */
function setupTouchDrag() {
    const sbLeft = document.getElementById('sb-left');
    if (!sbLeft) return;

    // Attach to any already-rendered items
    sbLeft.querySelectorAll('.project-item-child, .folder-drag-area').forEach(attachTouchDrag);

    // Watch for new items rendered by loadItems()
    const observer = new MutationObserver(mutations => {
        mutations.forEach(m => m.addedNodes.forEach(node => {
            if (!(node instanceof HTMLElement)) return;
            node.querySelectorAll('.project-item-child, .folder-drag-area').forEach(attachTouchDrag);
            if (node.matches?.('.project-item-child, .folder-drag-area')) attachTouchDrag(node);
        }));
    });
    observer.observe(sbLeft, { childList: true, subtree: true });
}

/**
 * Build ghost element cho touch drag — không clone, tự dựng icon + name.
 * Tránh phụ thuộc vào CSS context của sidebar (selector quá cụ thể gây icon vỡ).
 */
function buildTouchGhost(el) {
    const isFolder = el.classList.contains('folder-drag-area');

    // Lấy tên item
    const nameEl = el.querySelector('p');
    const name   = nameEl ? nameEl.textContent.trim() : '';

    // Lấy màu icon từ DOM
    let iconSvg;
    if (isFolder) {
        const color = el.querySelector('svg.folder-icon path')?.getAttribute('fill') || '#6366f1';
        iconSvg = `<svg viewBox="0 0 64 64" class="ghost-icon">
            <path d="M8 20 H22 L26 16 H44 Q50 16 50 22 V40 Q50 48 42 48 H16 Q8 48 8 40 Z" fill="${color}"/>
        </svg>`;
    } else {
        const color = el.querySelector('svg.project-icon circle')?.getAttribute('fill') || '#6366f1';
        iconSvg = `<svg viewBox="0 0 100 100" class="ghost-icon ghost-icon--dot">
            <circle cx="50" cy="50" r="40" fill="${color}"/>
        </svg>`;
    }

    const ghost = document.createElement('div');
    ghost.className = 'touch-drag-ghost';
    ghost.innerHTML = `${iconSvg}<span class="ghost-label">${name}</span>`;
    return ghost;
}

function attachTouchDrag(el) {
    if (el._touchDragBound) return;
    el._touchDragBound = true;

    const iid = el.dataset.iid;
    const HOLD_MS   = 300;   // ms giữ ngón tay để kích hoạt drag
    const MOVE_SLOP = 8;     // px di chuyển tối đa trong lúc chờ long-press

    let ghost      = null;
    let holdTimer  = null;
    let dragActive = false;  // true sau khi long-press xác nhận
    let isTouching = false;  // true khi đang có touch active (để guard dragstart)
    let startX = 0, startY = 0;
    let lastX  = 0, lastY  = 0;

    function cleanup(removeGhost) {
        clearTimeout(holdTimer); holdTimer = null;
        el.classList.remove('drag-ghost');           // khôi phục source element
        if (removeGhost && ghost) { ghost.remove(); ghost = null; }
        dragActive = false;
        isTouching = false;
        document.getElementById('cw')?.classList.remove('drag-over');
    }

    // BUG FIX #3: chỉ chặn native DnD khi đang touch (mobile) — desktop vẫn drag được
    el.addEventListener('dragstart', e => { if (isTouching) e.preventDefault(); });

    el.addEventListener('touchstart', e => {
        if (!iid) return;
        // BUG FIX #2: không restart nếu đang trong drag — tránh ngón tay thứ 2
        // chạm vào el reset dragActive=false khiến touchend bỏ qua addNode()
        if (dragActive) return;
        isTouching = true;
        const t0 = e.touches[0];
        startX = lastX = t0.clientX;
        startY = lastY = t0.clientY;
        dragActive = false;

        // Build ghost sạch (không clone) → tránh phụ thuộc CSS context của sidebar
        ghost = buildTouchGhost(el);
        ghost.style.opacity = '0';
        ghost.style.left = (t0.clientX - 40) + 'px';
        ghost.style.top  = (t0.clientY - 28) + 'px';
        document.body.appendChild(ghost);

        holdTimer = setTimeout(() => {
            holdTimer = null;
            dragActive = true;
            ghost.style.opacity = '0.88';
            el.classList.add('drag-ghost');          // source indicator: el gốc mờ + viền đứt
            if (navigator.vibrate) navigator.vibrate(30);
        }, HOLD_MS);
    }, { passive: true });

    el.addEventListener('touchmove', e => {
        const t0 = e.touches[0];
        lastX = t0.clientX;
        lastY = t0.clientY;

        if (!dragActive) {
            // Ngón tay di chuyển trước khi long-press xong → huỷ, cho scroll
            const dx = t0.clientX - startX, dy = t0.clientY - startY;
            if (Math.hypot(dx, dy) > MOVE_SLOP) {
                cleanup(true);
            }
            return; // KHÔNG gọi preventDefault → scroll hoạt động bình thường
        }

        // Drag đã active → chặn scroll, di chuyển ghost
        e.preventDefault();
        ghost.style.left = (t0.clientX - 40) + 'px';
        ghost.style.top  = (t0.clientY - 28) + 'px';
        document.getElementById('cw')?.classList.add('drag-over');
    }, { passive: false }); // phải false để có thể gọi preventDefault khi cần

    el.addEventListener('touchend', e => {
        clearTimeout(holdTimer); holdTimer = null;

        if (!dragActive || !iid) {
            cleanup(true);
            return;
        }

        // BUG FIX #4: dùng changedTouches để lấy vị trí chính xác khi nhấc ngón tay,
        // thay vì lastX/lastY từ touchmove cuối (có thể hơi lệch)
        const t0 = e.changedTouches?.[0];
        const tx = t0?.clientX ?? lastX;
        const ty = t0?.clientY ?? lastY;
        cleanup(true);

        closeAllMobSidebars();
        requestAnimationFrame(() => {
            const cwEl = document.getElementById('cw');
            if (!cwEl) return;
            const r = cwEl.getBoundingClientRect();
            const cx = (tx - r.left - panX) / zoom;
            const cy = (ty - r.top  - panY) / zoom;
            addNode(iid, cx - 80, cy - 36);
        });
    }, { passive: true });

    el.addEventListener('touchcancel', () => {
        cleanup(true);
    }, { passive: true });
}

// ═══════════════════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════════════════

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


// ── State ─────────────────────────────────────────────────────────────────────
let aiBarVisible  = false;
let aiLoading     = false;
let aiBackupState = null;   // { nodes, edges, nCnt } — backup trước khi apply diff
let aiPreviewMode = false;  // true khi đang xem preview, chờ confirm/cancel
 
// ── DOM refs (init sau DOMContentLoaded) ──────────────────────────────────────
let rmAiBar, rmAiInput, rmAiSend, rmAiToggle, rmPreviewBanner;
 
// =============================================================================
// INIT — gọi trong DOMContentLoaded (thêm `initAiBar()` vào block đó)
// =============================================================================
function initAiBar() {
    rmAiBar         = document.getElementById('rm-ai-bar');
    rmAiInput       = document.getElementById('rm-ai-input');
    rmAiSend        = document.getElementById('rm-ai-send');
    rmAiToggle      = document.getElementById('rm-ai-toggle');
    rmPreviewBanner = document.getElementById('rm-preview-banner');
 
    // Toggle button
    rmAiToggle.addEventListener('click', toggleAiBar);
 
    // Send on click
    rmAiSend.addEventListener('click', handleAiSend);
 
    // Send on Enter (Shift+Enter = newline)
    rmAiInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleAiSend();
        }
    });
 
    // Auto-resize textarea
    rmAiInput.addEventListener('input', () => {
        rmAiInput.style.height = '20px';
        rmAiInput.style.height = Math.min(rmAiInput.scrollHeight, 80) + 'px';
        rmAiInput.style.overflowY = rmAiInput.scrollHeight > 80 ? 'auto' : 'hidden';
    });
 
    // Preview banner buttons
    document.getElementById('rm-preview-cancel').addEventListener('click', cancelPreview);
    document.getElementById('rm-preview-save').addEventListener('click', commitPreview);
 
    // Esc huỷ preview
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && aiPreviewMode) cancelPreview();
    });
}
 
// =============================================================================
// TOGGLE AI BAR
// =============================================================================
function toggleAiBar() {
    aiBarVisible = !aiBarVisible;
    rmAiBar.classList.toggle('rm-ai-bar--hidden', !aiBarVisible);
    if (aiBarVisible) {
        rmAiInput.focus();
        rmAiToggle.title = 'Ẩn AI';
    } else {
        rmAiToggle.title = 'AI Edit';
    }
}
 
// =============================================================================
// BUILD CONTEXT — nén roadmap thành compact JSON gửi cho AI
// =============================================================================
function buildRoadmapContext() {
    const nodesSummary = Object.entries(nodes).map(([key, nd]) => ({
        key,
        name: nd.item.name,
        type: nd.item.type,
        ...(nd.item.parent_id ? { parent: nd.item.parent_id } : {})
    }));
 
    const edgesSummary = edges.map(e => `${e.from}→${e.to}`);
 
    // Lấy tên roadmap hiện tại
    const activeRm = roadmaps.find(r => r.id === activeRmId);
 
    return {
        id:            activeRmId,
        name:          activeRm?.name || 'Roadmap',
        nCnt:          nCnt,
        nodes_summary: nodesSummary,
        edges_summary: edgesSummary
    };
}
 
// =============================================================================
// SEND — Gửi request AI kèm context
// =============================================================================
async function handleAiSend() {
    const text = rmAiInput.value.trim();
    if (!text || aiLoading || aiPreviewMode) return;
    if (!activeRmId) {
        alert('Vui lòng chọn một roadmap trước.');
        return;
    }
 
    // Backup state trước khi thay đổi
    aiBackupState = {
        nodes: JSON.parse(JSON.stringify(nodes)),
        edges: JSON.parse(JSON.stringify(edges)),
        nCnt
    };
 
    setAiLoading(true);
    rmAiInput.value = '';
    rmAiInput.style.height = '20px';
 
    try {
        const ctx     = buildRoadmapContext();
        const payload = `[ROADMAP_CONTEXT]${JSON.stringify(ctx)}[/ROADMAP_CONTEXT]\n${text}`;
 
        // POST → AI xử lý bất đồng bộ
        const postRes = await utils.fetchWithAuth(`${API}/chatbot`, {
            method: 'POST',
            body: JSON.stringify({ message: payload })
        });
 
        if (!postRes.ok) throw new Error(`POST failed: ${postRes.status}`);
 
        // Poll GET /chatbot cho đến khi có response
        const aiData = await pollAiResponse();
 
        if (aiData?.type === 'roadmap_update' && aiData?.data) {
            applyRoadmapDiff(aiData.data);
        } else {
            // AI trả về message thường (không phải diff)
            showAiMessage(aiData?.content || 'Không có phản hồi.');
        }
 
    } catch (err) {
        console.error('[AI Bar]', err);
        showAiMessage('Có lỗi xảy ra, vui lòng thử lại.');
        aiBackupState = null;
    } finally {
        setAiLoading(false);
    }
}
 
// =============================================================================
// POLL — GET /chatbot với retry, timeout 30s
// =============================================================================
async function pollAiResponse(maxMs = 30000, intervalMs = 1200) {
    const deadline = Date.now() + maxMs;
 
    // Lấy timestamp message user vừa gửi làm mốc so sánh
    const sentAt = Date.now();
 
    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, intervalMs));
        try {
            const res = await utils.fetchWithAuth(`${API}/chatbot`);
            if (!res.ok) continue;
            const data = await res.json();
            // Chỉ nhận response mới (role=assistant và có nội dung)
            if (data?.role === 'assistant' && data?.content) {
                return data;
            }
        } catch (_) { /* tiếp tục retry */ }
    }
    throw new Error('AI timeout sau 30 giây');
}
 
// =============================================================================
// APPLY DIFF — Áp dụng diff lên canvas, vào preview mode
// =============================================================================
function applyRoadmapDiff(diffData) {
    const diff = diffData.diff;
    if (!diff) return;
 
    // 1. delete_nodes → remove DOM + data
    (diff.delete_nodes || []).forEach(nid => {
        document.getElementById('nd-' + nid)?.remove();
        delete nodes[nid];
    });
 
    // 2. delete_edges (by from+to)
    const toDelete = new Set(
        (diff.delete_edges || []).map(e => `${e.from}|${e.to}`)
    );
    edges = edges.filter(e => !toDelete.has(`${e.from}|${e.to}`));
 
    // 3. Auto-cleanup ghost edges (AI có thể quên delete edge của node đã xoá)
    const validKeys = new Set(Object.keys(nodes));
    edges = edges.filter(e => validKeys.has(e.from) && validKeys.has(e.to));
 
    // 4. update_nodes (partial merge)
    Object.entries(diff.update_nodes || {}).forEach(([nid, partial]) => {
        if (!nodes[nid]) return; // skip invalid node key
        // Deep merge: chỉ ghi đè những field có trong partial
        if (partial.x !== undefined) nodes[nid].x = partial.x;
        if (partial.y !== undefined) nodes[nid].y = partial.y;
        if (partial.item) {
            nodes[nid].item = { ...nodes[nid].item, ...partial.item };
        }
        // Re-render node element
        document.getElementById('nd-' + nid)?.remove();
        rebuildNode(nid, nodes[nid]);
        const el = document.getElementById('nd-' + nid);
        if (el) {
            el.style.left = nodes[nid].x + 'px';
            el.style.top  = nodes[nid].y + 'px';
        }
    });
 
    // 5. add_nodes
    Object.entries(diff.add_nodes || {}).forEach(([nid, nd]) => {
        nodes[nid] = nd;
        rebuildNode(nid, nd);
        const el = document.getElementById('nd-' + nid);
        if (el) {
            el.style.left = nd.x + 'px';
            el.style.top  = nd.y + 'px';
        }
        // Cập nhật nCnt nếu key mới lớn hơn
        const num = parseInt(nid.replace('n', ''), 10);
        if (!isNaN(num) && num > nCnt) nCnt = num;
    });
 
    // 6. add_edges
    (diff.add_edges || []).forEach(edge => {
        // Tránh duplicate edge
        const isDup = edges.some(e => e.from === edge.from && e.to === edge.to);
        if (!isDup && validKeys.has(edge.from) && validKeys.has(edge.to)) {
            edges.push(edge);
        }
    });
 
    // 7. Re-render toàn bộ edges + update empty state
    renderEdges();
    updateEmpty();
 
    // 8. Vào preview mode — lock canvas, show banner
    enterPreviewMode();
}
 
// =============================================================================
// PREVIEW MODE
// =============================================================================
function enterPreviewMode() {
    aiPreviewMode = true;
    document.getElementById('cw').classList.add('rm-preview-active');
    rmPreviewBanner.classList.remove('rm-preview-banner--hidden');
    // Ẩn AI bar trong lúc preview
    rmAiBar.classList.add('rm-ai-bar--hidden');
}
 
function exitPreviewMode() {
    aiPreviewMode = false;
    document.getElementById('cw').classList.remove('rm-preview-active');
    rmPreviewBanner.classList.add('rm-preview-banner--hidden');
    // Hiện lại AI bar nếu đang bật
    if (aiBarVisible) rmAiBar.classList.remove('rm-ai-bar--hidden');
}
 
function cancelPreview() {
    if (!aiBackupState) return;
    // Restore backup
    nodes = aiBackupState.nodes;
    edges = aiBackupState.edges;
    nCnt  = aiBackupState.nCnt;
    aiBackupState = null;
 
    // Rebuild toàn bộ canvas từ backup
    rebuildAllNodes();
    renderEdges();
    updateEmpty();
    exitPreviewMode();
}
 
async function commitPreview() {
    exitPreviewMode();
    aiBackupState = null;
    // Flush save ngay (không đợi debounce)
    await flushSave();
}
 
// =============================================================================
// REBUILD ALL NODES — xóa sạch canvas và vẽ lại từ nodes object
// =============================================================================
function rebuildAllNodes() {
    // Xóa tất cả node elements hiện tại
    document.querySelectorAll('[id^="nd-"]').forEach(el => el.remove());
    // Vẽ lại từ nodes
    Object.entries(nodes).forEach(([nid, nd]) => rebuildNode(nid, nd));
}
 
// =============================================================================
// UI HELPERS
// =============================================================================
function setAiLoading(on) {
    aiLoading = on;
    rmAiBar.classList.toggle('rm-ai-bar--loading', on);
    rmAiSend.disabled = on;
    rmAiInput.disabled = on;
}
 
function showAiMessage(text) {
    // Hiện message ngắn gọn trong hint-bar (tái dụng setHint đã có)
    setHint('🤖 ' + text);
    setTimeout(() => setHint('Kéo thả để thêm · Click nền để di chuyển · Ctrl + Scroll để zoom'), 4000);
}
