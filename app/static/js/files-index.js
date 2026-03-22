document.addEventListener("DOMContentLoaded", () => {
    const workspace = document.getElementById("filesWorkspace");
    if (!workspace) {
        return;
    }

    const VIEW_STORAGE_KEY = "home-cloud-files-view";
    const FILTER_STORAGE_KEY = "home-cloud-files-filters";
    const dom = {
        activeFilters: document.getElementById("workspaceActiveFilters"),
        batchActionsGroup: document.getElementById("batchActionsGroup"),
        batchOperationsForm: document.getElementById("batchOperationsForm"),
        clearFiltersBtn: document.getElementById("clearFiltersBtn"),
        clearFiltersEmptyBtn: document.getElementById("clearFiltersEmptyBtn"),
        clearRecentUploadsBtn: document.getElementById("clearRecentUploadsBtn"),
        clearSearchResultsBtn: document.getElementById("clearSearchResultsBtn"),
        clientFilterInput: document.getElementById("clientFilterInput"),
        currentFileName: document.getElementById("currentFileName"),
        deleteFileForm: document.getElementById("deleteFileForm"),
        deleteFileName: document.getElementById("deleteFileName"),
        deleteFolderForm: document.getElementById("deleteFolderForm"),
        deleteFolderName: document.getElementById("deleteFolderName"),
        destinationSelect: document.getElementById("destinationSelect"),
        dismissWorkspaceFeedback: document.getElementById("dismissWorkspaceFeedback"),
        emptyState: document.getElementById("workspaceEmptyState"),
        errorModalBody: document.getElementById("errorModalBody"),
        errorModalTitle: document.getElementById("errorModalTitle"),
        fileCountMetric: document.getElementById("fileCountMetric"),
        fileInput: document.getElementById("files"),
        fileProgressBar: document.getElementById("fileProgressBar"),
        filesDropzone: document.getElementById("filesDropzone"),
        filterEmptyState: document.getElementById("filterEmptyState"),
        filterStatus: document.getElementById("filterStatus"),
        folderCountMetric: document.getElementById("folderCountMetric"),
        folderInput: document.getElementById("folder"),
        folderUploadFlag: document.getElementById("folderUploadFlag"),
        focusRecentUploadsBtn: document.getElementById("focusRecentUploadsBtn"),
        moveSelectedBtn: document.getElementById("moveSelectedBtn"),
        recentUploadsFilterBtn: document.getElementById("recentUploadsFilterBtn"),
        renameFileForm: document.getElementById("renameFileForm"),
        renameFolderForm: document.getElementById("renameFolderForm"),
        searchResultsContainer: document.getElementById("searchResultsContainer"),
        searchResultsLabel: document.getElementById("searchResultsLabel"),
        searchResultsShell: document.getElementById("searchResultsShell"),
        selectAllBtn: document.getElementById("selectAllBtn"),
        selectAllCheckbox: document.getElementById("selectAllCheckbox"),
        selectedItemsContainer: document.getElementById("selectedItemsContainer"),
        selectionStatus: document.getElementById("selectionStatus"),
        sortSelect: document.getElementById("sortSelect"),
        storageUsageBar: document.getElementById("storageUsageBar"),
        storageUsageNote: document.getElementById("storageUsageNote"),
        storageUsageValue: document.getElementById("storageUsageValue"),
        tableBody: document.getElementById("workspaceTableBody"),
        totalProgressBar: document.getElementById("totalProgressBar"),
        typeFilterSelect: document.getElementById("typeFilterSelect"),
        uploadedCount: document.getElementById("uploadedCount"),
        uploadingFiles: document.getElementById("uploadingFiles"),
        uploadButton: document.getElementById("uploadButton"),
        uploadForm: document.getElementById("uploadForm"),
        uploadModal: document.getElementById("uploadModal"),
        uploadSelectionList: document.getElementById("uploadSelectionList"),
        uploadSelectionMeta: document.getElementById("uploadSelectionMeta"),
        uploadSelectionSummary: document.getElementById("uploadSelectionSummary"),
        uploadSelectionTitle: document.getElementById("uploadSelectionTitle"),
        viewGridButton: document.getElementById("view-grid"),
        viewListButton: document.getElementById("view-list"),
        visibleCountMetric: document.getElementById("visibleCountMetric"),
        workspaceBulkControls: document.getElementById("workspaceBulkControls"),
        workspaceFeedback: document.getElementById("workspaceFeedback"),
        workspaceFeedbackActions: document.getElementById("workspaceFeedbackActions"),
        workspaceFeedbackIcon: document.getElementById("workspaceFeedbackIcon"),
        workspaceFeedbackMessage: document.getElementById("workspaceFeedbackMessage"),
        workspaceFeedbackTitle: document.getElementById("workspaceFeedbackTitle"),
        workspaceSearchForm: document.getElementById("workspaceSearchForm"),
        workspaceSearchInput: document.getElementById("workspaceSearchInput"),
    };

    const modals = {
        deleteFile: getModalInstance("deleteFileModal"),
        deleteFolder: getModalInstance("deleteFolderModal"),
        error: getModalInstance("errorModal"),
        move: getModalInstance("moveModal"),
        renameFile: getModalInstance("renameFileModal"),
        renameFolder: getModalInstance("renameFolderModal"),
        upload: getModalInstance("uploadModal"),
    };

    let recentUploadKeys = new Set();
    let recentFilterActive = false;
    let uploadStartTime = 0;
    let revealAnimationEnabled = false;

    function getModalInstance(id) {
        if (!window.bootstrap) {
            return null;
        }

        const element = document.getElementById(id);
        return element ? window.bootstrap.Modal.getOrCreateInstance(element) : null;
    }

    function rowKey(row) {
        return `${row.dataset.kind}-${row.dataset.itemId}`;
    }

    function getRows() {
        return Array.from(dom.tableBody.querySelectorAll("tr[data-kind]"));
    }

    function escapeHtml(value) {
        return value
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function formatBytes(bytes) {
        if (!Number.isFinite(bytes) || bytes <= 0) {
            return "0 B";
        }

        const units = ["B", "KB", "MB", "GB", "TB"];
        let value = bytes;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value /= 1024;
            unitIndex += 1;
        }

        const precision = value >= 100 || unitIndex === 0 ? 0 : 1;
        return `${value.toFixed(precision)} ${units[unitIndex]}`;
    }

    function updateWorkspaceFeedback(feedback, hasRecentUploads = false) {
        if (!dom.workspaceFeedback || !feedback) {
            return;
        }

        dom.workspaceFeedback.dataset.state = feedback.state || "progress";
        dom.workspaceFeedbackTitle.textContent = feedback.title || "Update";
        dom.workspaceFeedbackMessage.textContent = feedback.message || "";

        dom.workspaceFeedbackIcon.className = "fas";
        if (feedback.state === "success") {
            dom.workspaceFeedbackIcon.classList.add("fa-circle-check");
        } else if (feedback.state === "error") {
            dom.workspaceFeedbackIcon.classList.add("fa-triangle-exclamation");
        } else {
            dom.workspaceFeedbackIcon.classList.add("fa-circle-info");
        }

        dom.workspaceFeedback.classList.remove("d-none");
        dom.workspaceFeedbackActions.classList.toggle("d-none", !hasRecentUploads);
    }

    function hideWorkspaceFeedback() {
        if (dom.workspaceFeedback) {
            dom.workspaceFeedback.classList.add("d-none");
        }
    }

    function showErrorModal(title, message) {
        if (dom.errorModalTitle) {
            dom.errorModalTitle.textContent = title;
        }
        if (dom.errorModalBody) {
            dom.errorModalBody.textContent = message;
        }

        if (modals.error) {
            modals.error.show();
        }
    }

    function buildActionUrl(template, itemId) {
        return template.endsWith("0")
            ? `${template.slice(0, -1)}${itemId}`
            : template.replace("0", String(itemId));
    }

    function updateMetrics(metrics) {
        if (!metrics) {
            return;
        }

        dom.storageUsageValue.textContent = metrics.storage_value;
        dom.storageUsageNote.textContent = metrics.storage_note;
        dom.storageUsageBar.textContent = `${metrics.storage_percent}%`;
        dom.storageUsageBar.style.width = `${metrics.storage_percent}%`;
        dom.storageUsageBar.setAttribute("aria-valuenow", String(metrics.storage_percent));
        dom.storageUsageBar.className = `progress-bar ${metrics.storage_bar_class}`;
        dom.folderCountMetric.textContent = String(metrics.folders_count);
        dom.fileCountMetric.textContent = String(metrics.files_count);
        dom.visibleCountMetric.textContent = String(metrics.visible_count);
    }

    function replaceTableBody(rowsHtml) {
        dom.tableBody.innerHTML = rowsHtml;
        revealAnimationEnabled = true;
        markRecentUploads();
        applyWorkspaceFilters();
        updateSelectionState();
    }

    function replaceDestinationOptions(optionsHtml) {
        if (dom.destinationSelect) {
            dom.destinationSelect.innerHTML = optionsHtml;
        }
    }

    function getSortedRows(rows) {
        const sortValue = dom.sortSelect?.value || "name-asc";
        const sortedRows = [...rows];

        sortedRows.sort((rowA, rowB) => {
            const nameA = rowA.dataset.name || "";
            const nameB = rowB.dataset.name || "";
            const updatedA = Date.parse(rowA.dataset.updated || "") || 0;
            const updatedB = Date.parse(rowB.dataset.updated || "") || 0;
            const sizeA = Number.parseInt(rowA.dataset.sizeBytes || "0", 10);
            const sizeB = Number.parseInt(rowB.dataset.sizeBytes || "0", 10);
            const typeA = rowA.dataset.type || "";
            const typeB = rowB.dataset.type || "";

            switch (sortValue) {
                case "name-desc":
                    return nameB.localeCompare(nameA);
                case "updated-desc":
                    return updatedB - updatedA;
                case "updated-asc":
                    return updatedA - updatedB;
                case "size-desc":
                    return sizeB - sizeA;
                case "size-asc":
                    return sizeA - sizeB;
                case "type-asc":
                    return typeA.localeCompare(typeB) || nameA.localeCompare(nameB);
                case "name-asc":
                default:
                    return nameA.localeCompare(nameB);
            }
        });

        return sortedRows;
    }

    function updateFilterStatus(visibleCount, totalCount) {
        const fragments = [`${visibleCount} of ${totalCount} item(s) shown`];
        const keyword = dom.clientFilterInput?.value.trim();
        const typeValue = dom.typeFilterSelect?.value;

        if (keyword) {
            fragments.push(`keyword "${keyword}"`);
        }
        if (typeValue && typeValue !== "all") {
            fragments.push(`type "${typeValue}"`);
        }
        if (recentFilterActive) {
            fragments.push("recent uploads");
        }

        dom.filterStatus.textContent = fragments.join(" | ");
    }

    function renderActiveFilters(keyword, typeValue) {
        if (!dom.activeFilters) {
            return;
        }

        const chips = [];
        if (keyword) {
            chips.push(`<span class="workspace-filter-pill"><i class="fas fa-keyboard"></i>Keyword: ${escapeHtml(keyword)}</span>`);
        }
        if (typeValue && typeValue !== "all") {
            chips.push(`<span class="workspace-filter-pill"><i class="fas fa-tag"></i>Type: ${escapeHtml(typeValue)}</span>`);
        }
        if (recentFilterActive) {
            chips.push('<span class="workspace-filter-pill"><i class="fas fa-sparkles"></i>Recent uploads</span>');
        }

        dom.activeFilters.innerHTML = chips.join("");
        dom.activeFilters.classList.toggle("d-none", chips.length === 0);
    }

    function persistFilters() {
        const state = {
            keyword: dom.clientFilterInput?.value || "",
            type: dom.typeFilterSelect?.value || "all",
            sort: dom.sortSelect?.value || "name-asc",
            recent: recentFilterActive,
        };
        window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(state));
    }

    function restoreFilters() {
        const raw = window.localStorage.getItem(FILTER_STORAGE_KEY);
        if (!raw) {
            return;
        }

        try {
            const state = JSON.parse(raw);
            if (dom.clientFilterInput && typeof state.keyword === "string") {
                dom.clientFilterInput.value = state.keyword;
            }
            if (dom.typeFilterSelect && typeof state.type === "string") {
                dom.typeFilterSelect.value = state.type;
            }
            if (dom.sortSelect && typeof state.sort === "string") {
                dom.sortSelect.value = state.sort;
            }
            recentFilterActive = Boolean(state.recent);
        } catch (error) {
            window.localStorage.removeItem(FILTER_STORAGE_KEY);
        }
    }

    function updateWorkspaceChrome(totalCount, visibleCount) {
        const hasItems = totalCount > 0;
        const hasVisibleItems = visibleCount > 0;

        dom.emptyState.classList.toggle("d-none", hasItems);
        dom.batchOperationsForm.classList.toggle("d-none", !hasItems);
        dom.workspaceBulkControls.classList.toggle("d-none", !hasItems);
        dom.filterEmptyState.classList.toggle("d-none", !hasItems || hasVisibleItems);
        dom.visibleCountMetric.textContent = String(visibleCount);

        if (!hasItems) {
            recentFilterActive = false;
        }
    }

    function getVisibleCheckboxes() {
        return getRows()
            .filter((row) => !row.classList.contains("d-none"))
            .map((row) => row.querySelector(".item-select"))
            .filter(Boolean);
    }

    function updateSelectionState() {
        const visibleCheckboxes = getVisibleCheckboxes();
        const selectedCount = visibleCheckboxes.filter((checkbox) => checkbox.checked).length;
        const totalVisible = visibleCheckboxes.length;

        if (dom.selectionStatus) {
            dom.selectionStatus.textContent =
                selectedCount > 0
                    ? `${selectedCount} item(s) selected`
                    : `${totalVisible} item(s) available`;
        }

        if (dom.batchActionsGroup) {
            dom.batchActionsGroup.classList.toggle("d-none", selectedCount === 0);
        }

        if (dom.selectAllCheckbox) {
            dom.selectAllCheckbox.checked = totalVisible > 0 && selectedCount === totalVisible;
            dom.selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < totalVisible;
        }
    }

    function applyWorkspaceFilters() {
        const rows = getSortedRows(getRows());
        const keyword = (dom.clientFilterInput?.value || "").trim().toLowerCase();
        const rawKeyword = dom.clientFilterInput?.value.trim() || "";
        const typeValue = dom.typeFilterSelect?.value || "all";
        let visibleCount = 0;

        rows.forEach((row) => {
            const rowKind = row.dataset.kind || "";
            const rowType = row.dataset.type || "";
            const matchesKeyword = !keyword || (row.dataset.name || "").includes(keyword);
            const matchesType =
                typeValue === "all" ||
                rowKind === typeValue ||
                rowType === typeValue;
            const matchesRecent = !recentFilterActive || recentUploadKeys.has(rowKey(row));
            const shouldShow = matchesKeyword && matchesType && matchesRecent;
            const checkbox = row.querySelector(".item-select");

            row.classList.toggle("d-none", !shouldShow);
            dom.tableBody.appendChild(row);
            row.classList.toggle("row-revealed", revealAnimationEnabled && shouldShow);

            if (!shouldShow && checkbox) {
                checkbox.checked = false;
            }

            if (shouldShow) {
                visibleCount += 1;
            }
        });

        updateWorkspaceChrome(rows.length, visibleCount);
        updateFilterStatus(visibleCount, rows.length);
        renderActiveFilters(rawKeyword, typeValue);
        persistFilters();
        updateSelectionState();
        revealAnimationEnabled = false;
    }

    function setView(view) {
        workspace.classList.toggle("grid-view", view === "grid");
        dom.viewGridButton.classList.toggle("active", view === "grid");
        dom.viewListButton.classList.toggle("active", view === "list");
        window.localStorage.setItem(VIEW_STORAGE_KEY, view);
    }

    function resetSearchResults() {
        if (dom.searchResultsShell) {
            dom.searchResultsShell.classList.add("d-none");
        }
        if (dom.searchResultsContainer) {
            dom.searchResultsContainer.innerHTML = "";
        }
        if (dom.searchResultsLabel) {
            dom.searchResultsLabel.textContent = "Search results";
        }
    }

    function highlightSearchMatches(query) {
        const normalizedQuery = query.trim().toLowerCase();
        if (!normalizedQuery) {
            return;
        }

        dom.searchResultsContainer.querySelectorAll(".search-match-target").forEach((element) => {
            const originalText = element.textContent || "";
            const matchIndex = originalText.toLowerCase().indexOf(normalizedQuery);
            if (matchIndex === -1) {
                return;
            }

            const start = escapeHtml(originalText.slice(0, matchIndex));
            const middle = escapeHtml(originalText.slice(matchIndex, matchIndex + normalizedQuery.length));
            const end = escapeHtml(originalText.slice(matchIndex + normalizedQuery.length));
            element.innerHTML = `${start}<span class="search-hit">${middle}</span>${end}`;
        });
    }

    function markRecentUploads() {
        getRows().forEach((row) => {
            row.classList.toggle("recent-upload", recentUploadKeys.has(rowKey(row)));
        });

        const hasRecentUploads = recentUploadKeys.size > 0;
        if (dom.recentUploadsFilterBtn) {
            dom.recentUploadsFilterBtn.classList.toggle("d-none", !hasRecentUploads);
            dom.recentUploadsFilterBtn.classList.toggle("active", recentFilterActive);
            dom.recentUploadsFilterBtn.setAttribute("aria-pressed", String(recentFilterActive));
        }
    }

    function clearRecentUploads() {
        recentUploadKeys = new Set();
        recentFilterActive = false;
        markRecentUploads();
        applyWorkspaceFilters();
        dom.workspaceFeedbackActions.classList.add("d-none");
    }

    function getActiveUploadMode() {
        return document.getElementById("folder-tab")?.classList.contains("active") ? "folder" : "files";
    }

    function getActiveUploadInput() {
        return getActiveUploadMode() === "folder" ? dom.folderInput : dom.fileInput;
    }

    function syncUploadMode() {
        const isFolderMode = getActiveUploadMode() === "folder";
        if (dom.folderUploadFlag) {
            dom.folderUploadFlag.disabled = !isFolderMode;
        }
        renderUploadSelection();
    }

    function clearFileInput(input) {
        if (input) {
            input.value = "";
        }
    }

    function renderUploadSelection() {
        const activeInput = getActiveUploadInput();
        const files = activeInput?.files ? Array.from(activeInput.files) : [];
        const totalSize = files.reduce((sum, file) => sum + (file.size || 0), 0);

        dom.uploadSelectionList.innerHTML = "";
        dom.uploadSelectionSummary.classList.toggle("d-none", files.length === 0);
        dom.uploadButton.disabled = files.length === 0;

        if (files.length === 0) {
            dom.uploadSelectionMeta.textContent = "";
            dom.uploadSelectionTitle.textContent = "Selection ready";
            return;
        }

        dom.uploadSelectionTitle.textContent =
            getActiveUploadMode() === "folder" ? "Folder upload ready" : "Upload queue ready";
        dom.uploadSelectionMeta.textContent = `${files.length} item(s) | ${formatBytes(totalSize)}`;

        files.slice(0, 5).forEach((file) => {
            const entry = document.createElement("li");
            const label = document.createElement("span");
            label.textContent = file.webkitRelativePath || file.name;
            const meta = document.createElement("span");
            meta.textContent = formatBytes(file.size || 0);
            entry.append(label, meta);
            dom.uploadSelectionList.appendChild(entry);
        });

        if (files.length > 5) {
            const entry = document.createElement("li");
            const label = document.createElement("span");
            label.textContent = `+${files.length - 5} more item(s)`;
            const meta = document.createElement("span");
            meta.textContent = "Queued";
            entry.append(label, meta);
            dom.uploadSelectionList.appendChild(entry);
        }
    }

    function resetUploadProgress() {
        dom.uploadingFiles.classList.add("d-none");
        dom.fileProgressBar.style.width = "0%";
        dom.fileProgressBar.textContent = "0%";
        dom.fileProgressBar.setAttribute("aria-valuenow", "0");
        dom.totalProgressBar.style.width = "0%";
        dom.totalProgressBar.textContent = "0%";
        dom.totalProgressBar.setAttribute("aria-valuenow", "0");
        dom.currentFileName.textContent = "Uploading...";
        dom.uploadedCount.textContent = "0/0 files";
        document.getElementById("uploadSpeed").textContent = "0 KB/s";
    }

    function setUploadBusy(isBusy) {
        dom.uploadButton.disabled = isBusy || !(getActiveUploadInput()?.files?.length);
        dom.uploadButton.textContent = isBusy ? "Uploading..." : "Upload";
    }

    function updateUploadProgress(event, fileCount, fileNames) {
        if (!event.lengthComputable) {
            return;
        }

        const percent = Math.round((event.loaded / event.total) * 100);
        const elapsedMs = Math.max(performance.now() - uploadStartTime, 1);
        const speedBytesPerSecond = (event.loaded / elapsedMs) * 1000;

        dom.uploadingFiles.classList.remove("d-none");
        dom.fileProgressBar.style.width = `${percent}%`;
        dom.fileProgressBar.textContent = `${percent}%`;
        dom.fileProgressBar.setAttribute("aria-valuenow", String(percent));
        dom.totalProgressBar.style.width = `${percent}%`;
        dom.totalProgressBar.textContent = `${percent}%`;
        dom.totalProgressBar.setAttribute("aria-valuenow", String(percent));
        dom.currentFileName.textContent =
            fileCount === 1 ? fileNames[0] : `Processing ${fileCount} item(s)`;
        dom.uploadedCount.textContent = `${Math.max(1, Math.round((percent / 100) * fileCount))}/${fileCount} files`;
        document.getElementById("uploadSpeed").textContent = `${formatBytes(speedBytesPerSecond)}/s`;
    }

    function setRecentUploads(recentItems) {
        recentUploadKeys = new Set(
            (recentItems || []).map((item) => `${item.kind}-${item.id}`)
        );
        recentFilterActive = recentUploadKeys.size > 0;
        markRecentUploads();
    }

    function submitUploadForm(event) {
        event.preventDefault();

        const activeInput = getActiveUploadInput();
        const selectedFiles = activeInput?.files ? Array.from(activeInput.files) : [];
        if (selectedFiles.length === 0) {
            showErrorModal("Upload Error", "Choose at least one file or folder before starting the upload.");
            return;
        }

        const formData = new FormData(dom.uploadForm);
        if (getActiveUploadMode() !== "folder") {
            formData.delete("is_folder_upload");
        }

        const xhr = new XMLHttpRequest();
        uploadStartTime = performance.now();
        resetUploadProgress();
        setUploadBusy(true);

        xhr.upload.addEventListener("progress", (progressEvent) => {
            updateUploadProgress(
                progressEvent,
                selectedFiles.length,
                selectedFiles.map((file) => file.name)
            );
        });

        xhr.addEventListener("load", () => {
            setUploadBusy(false);

            let payload = null;
            try {
                payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
            } catch (error) {
                payload = null;
            }

            if (xhr.status >= 200 && xhr.status < 300 && payload) {
                if (payload.rows_html) {
                    replaceTableBody(payload.rows_html);
                }
                replaceDestinationOptions(payload.destination_options_html);
                updateMetrics(payload.metrics);
                setRecentUploads(payload.recent_items);
                updateWorkspaceFeedback(payload.feedback, recentUploadKeys.size > 0);
                dom.uploadForm.reset();
                clearFileInput(dom.fileInput);
                clearFileInput(dom.folderInput);
                resetUploadProgress();
                renderUploadSelection();
                if (modals.upload) {
                    modals.upload.hide();
                }
                return;
            }

            const feedback = payload?.feedback;
            const fallbackMessage =
                feedback?.message || "The upload could not be completed. Review the request and try again.";
            updateWorkspaceFeedback(
                feedback || {
                    state: "error",
                    title: "Upload failed",
                    message: fallbackMessage,
                }
            );
            showErrorModal(feedback?.title || "Upload Error", fallbackMessage);
        });

        xhr.addEventListener("error", () => {
            setUploadBusy(false);
            updateWorkspaceFeedback({
                state: "error",
                title: "Upload failed",
                message: "The server did not respond while uploading. Try again.",
            });
            showErrorModal("Upload Error", "The server did not respond while uploading. Try again.");
        });

        xhr.open("POST", dom.uploadForm.action, true);
        xhr.setRequestHeader("Accept", "application/json");
        xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
        xhr.send(formData);
    }

    function toggleRecentUploadsFilter() {
        if (recentUploadKeys.size === 0) {
            return;
        }

        recentFilterActive = !recentFilterActive;
        markRecentUploads();
        applyWorkspaceFilters();
    }

    function handleGlobalShortcuts(event) {
        const target = event.target;
        const isEditable =
            target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement ||
            target instanceof HTMLSelectElement ||
            target?.isContentEditable;

        if (event.key === "/" && !isEditable) {
            event.preventDefault();
            dom.workspaceSearchInput?.focus();
            dom.workspaceSearchInput?.select();
            return;
        }

        if (event.key === "Escape") {
            if (!dom.searchResultsShell?.classList.contains("d-none")) {
                resetSearchResults();
                return;
            }
            if (recentFilterActive) {
                recentFilterActive = false;
                markRecentUploads();
                applyWorkspaceFilters();
            }
        }
    }

    function handleWorkspaceClick(event) {
        const button = event.target.closest("button, a");
        if (!button) {
            return;
        }

        if (button === dom.viewGridButton) {
            setView("grid");
            return;
        }

        if (button === dom.viewListButton) {
            setView("list");
            return;
        }

        if (button === dom.selectAllBtn) {
            const shouldCheck = getVisibleCheckboxes().some((checkbox) => !checkbox.checked);
            getVisibleCheckboxes().forEach((checkbox) => {
                checkbox.checked = shouldCheck;
            });
            updateSelectionState();
            return;
        }

        if (button === dom.moveSelectedBtn) {
            const selectedItems = getVisibleCheckboxes()
                .filter((checkbox) => checkbox.checked)
                .map((checkbox) => checkbox.value);

            if (selectedItems.length === 0) {
                return;
            }

            dom.selectedItemsContainer.innerHTML = "";
            selectedItems.forEach((value) => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "selected_items[]";
                input.value = value;
                dom.selectedItemsContainer.appendChild(input);
            });
            modals.move?.show();
            return;
        }

        if (button.id === "deleteSelectedBtn") {
            if (!window.confirm("Move the selected items to trash?")) {
                return;
            }
            dom.batchOperationsForm.action = workspace.dataset.batchDeleteUrl;
            dom.batchOperationsForm.submit();
            return;
        }

        if (button === dom.recentUploadsFilterBtn || button === dom.focusRecentUploadsBtn) {
            toggleRecentUploadsFilter();
            return;
        }

        if (button === dom.clearRecentUploadsBtn) {
            clearRecentUploads();
            return;
        }

        if (button === dom.clearSearchResultsBtn) {
            resetSearchResults();
            return;
        }

        if (button === dom.dismissWorkspaceFeedback) {
            hideWorkspaceFeedback();
            return;
        }

        if (button === dom.clearFiltersBtn || button === dom.clearFiltersEmptyBtn) {
            dom.clientFilterInput.value = "";
            dom.typeFilterSelect.value = "all";
            dom.sortSelect.value = "name-asc";
            recentFilterActive = false;
            markRecentUploads();
            applyWorkspaceFilters();
            return;
        }

        if (button === dom.filesDropzone) {
            dom.fileInput?.click();
            return;
        }

        if (button.id === "clearUploadSelectionBtn") {
            clearFileInput(dom.fileInput);
            clearFileInput(dom.folderInput);
            renderUploadSelection();
            resetUploadProgress();
            return;
        }

        if (button.classList.contains("delete-file")) {
            dom.deleteFileName.textContent = button.dataset.fileName || "";
            dom.deleteFileForm.action = buildActionUrl(
                workspace.dataset.deleteFileUrlTemplate,
                button.dataset.fileId
            );
            modals.deleteFile?.show();
            return;
        }

        if (button.classList.contains("delete-folder")) {
            dom.deleteFolderName.textContent = button.dataset.folderName || "";
            dom.deleteFolderForm.action = buildActionUrl(
                workspace.dataset.deleteFolderUrlTemplate,
                button.dataset.folderId
            );
            modals.deleteFolder?.show();
            return;
        }

        if (button.classList.contains("rename-file")) {
            dom.renameFileForm.action = buildActionUrl(
                workspace.dataset.renameFileUrlTemplate,
                button.dataset.fileId
            );
            const input = document.getElementById("newFileName");
            if (input) {
                input.value = button.dataset.fileName || "";
            }
            modals.renameFile?.show();
            return;
        }

        if (button.classList.contains("rename-folder")) {
            dom.renameFolderForm.action = buildActionUrl(
                workspace.dataset.renameFolderUrlTemplate,
                button.dataset.folderId
            );
            const input = document.getElementById("newFolderName");
            if (input) {
                input.value = button.dataset.folderName || "";
            }
            modals.renameFolder?.show();
            return;
        }

        if (button.classList.contains("download-folder")) {
            window.location.href = buildActionUrl(
                workspace.dataset.downloadFolderUrlTemplate,
                button.dataset.folderId
            );
        }
    }

    function handleWorkspaceChange(event) {
        if (event.target === dom.selectAllCheckbox) {
            getVisibleCheckboxes().forEach((checkbox) => {
                checkbox.checked = event.target.checked;
            });
            updateSelectionState();
            return;
        }

        if (event.target.classList.contains("item-select")) {
            updateSelectionState();
            return;
        }

        if (event.target === dom.fileInput || event.target === dom.folderInput) {
            renderUploadSelection();
        }
    }

    async function submitSearchForm(event) {
        event.preventDefault();

        const query = dom.workspaceSearchInput?.value.trim() || "";
        if (!query) {
            resetSearchResults();
            return;
        }

        dom.workspaceSearchForm.classList.add("is-loading");

        try {
            const url = `${workspace.dataset.searchUrl}?query=${encodeURIComponent(query)}`;
            const response = await fetch(url, {
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });

            if (!response.ok) {
                throw new Error(`Search request failed with ${response.status}`);
            }

            const payload = await response.json();
            dom.searchResultsContainer.innerHTML = payload.html;
            dom.searchResultsShell.classList.remove("d-none");
            dom.searchResultsLabel.textContent = `${payload.total_count} result(s) for "${payload.query}"`;
            highlightSearchMatches(payload.query);
            dom.searchResultsShell.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error) {
            showErrorModal("Search Error", "Search results could not be loaded. Try again.");
        } finally {
            dom.workspaceSearchForm.classList.remove("is-loading");
        }
    }

    function bindDropzoneEvents() {
        if (!dom.filesDropzone || !dom.fileInput) {
            return;
        }

        ["dragenter", "dragover"].forEach((eventName) => {
            dom.filesDropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dom.filesDropzone.classList.add("is-dragover");
            });
        });

        ["dragleave", "drop"].forEach((eventName) => {
            dom.filesDropzone.addEventListener(eventName, () => {
                dom.filesDropzone.classList.remove("is-dragover");
            });
        });

        dom.filesDropzone.addEventListener("drop", (event) => {
            event.preventDefault();
            if (event.dataTransfer?.files?.length) {
                dom.fileInput.files = event.dataTransfer.files;
                renderUploadSelection();
            }
        });
    }

    workspace.addEventListener("click", handleWorkspaceClick);
    workspace.addEventListener("change", handleWorkspaceChange);
    dom.clientFilterInput?.addEventListener("input", applyWorkspaceFilters);
    dom.typeFilterSelect?.addEventListener("change", applyWorkspaceFilters);
    dom.sortSelect?.addEventListener("change", applyWorkspaceFilters);
    dom.workspaceSearchForm?.addEventListener("submit", submitSearchForm);
    dom.uploadForm?.addEventListener("submit", submitUploadForm);
    document.getElementById("files-tab")?.addEventListener("shown.bs.tab", syncUploadMode);
    document.getElementById("folder-tab")?.addEventListener("shown.bs.tab", syncUploadMode);
    dom.uploadModal?.addEventListener("hidden.bs.modal", () => {
        resetUploadProgress();
        setUploadBusy(false);
        clearFileInput(dom.fileInput);
        clearFileInput(dom.folderInput);
        renderUploadSelection();
    });
    document.addEventListener("keydown", handleGlobalShortcuts);

    bindDropzoneEvents();
    syncUploadMode();
    restoreFilters();
    markRecentUploads();
    setView(window.localStorage.getItem(VIEW_STORAGE_KEY) || "list");
    applyWorkspaceFilters();
});
