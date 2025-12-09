document.addEventListener("DOMContentLoaded", () => {
  // ───────────────────────────────────────────────
  // Patient search filter
  // ───────────────────────────────────────────────
  const searchInput = document.querySelector("#patient-search");
  const patientRows = document.querySelectorAll("#patients-table tbody tr");

  if (searchInput && patientRows.length) {
    searchInput.addEventListener("input", (event) => {
      const term = String(event.target.value || "").trim().toLowerCase();

      patientRows.forEach((row) => {
        const name = String(row.dataset.name || "").toLowerCase();
        const phone = String(row.dataset.phone || "").toLowerCase();

        if (!term || name.includes(term) || phone.includes(term)) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      });
    });
  }

  // ───────────────────────────────────────────────
  // Patient CRUD modal controls
  // ───────────────────────────────────────────────
  const patientModal = document.querySelector("#patient-modal");
  const patientModalTitle = document.querySelector("#patient-modal-title");
  const patientModalClose = document.querySelector("#patient-modal-close");
  const patientModalCancel = document.querySelector("#patient-modal-cancel");
  const openAddPatientBtn = document.querySelector("#open-add-patient");

  const patientFieldId = document.querySelector("#patient-id");
  const patientFieldName = document.querySelector("#patient-name");
  const patientFieldPhone = document.querySelector("#patient-phone");
  const patientFieldEmail = document.querySelector("#patient-email");

  const patientEditButtons = document.querySelectorAll(".btn-edit-patient");
  const patientDeleteButtons = document.querySelectorAll(".btn-delete-patient");

  const openPatientModal = (mode, data) => {
    if (!patientModal) return;

    if (mode === "edit") {
      patientModalTitle.textContent = "Edit patient";
      patientFieldId.value = data.id || "";
      patientFieldName.value = data.name || "";
      patientFieldPhone.value = data.phone || "";
      patientFieldEmail.value = data.email || "";
    } else {
      patientModalTitle.textContent = "Add patient";
      patientFieldId.value = "";
      patientFieldName.value = "";
      patientFieldPhone.value = "";
      patientFieldEmail.value = "";
    }

    patientModal.classList.remove("modal--hidden");
  };

  const closePatientModal = () => {
    if (!patientModal) return;
    patientModal.classList.add("modal--hidden");
  };

  if (openAddPatientBtn) {
    openAddPatientBtn.addEventListener("click", () => openPatientModal("add", {}));
  }

  if (patientModalClose) {
    patientModalClose.addEventListener("click", closePatientModal);
  }

  if (patientModalCancel) {
    patientModalCancel.addEventListener("click", (event) => {
      event.preventDefault();
      closePatientModal();
    });
  }

  if (patientModal) {
    const backdrop = patientModal.querySelector(".modal__backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", closePatientModal);
    }
  }

  patientEditButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id || "";
      const name = btn.dataset.name || "";
      const phone = btn.dataset.phone || "";
      const email = btn.dataset.email || "";

      openPatientModal("edit", { id, name, phone, email });
    });
  });

  patientDeleteButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const form = btn.closest("form");
      if (!form) return;

      const name =
        btn.closest("tr")?.querySelector("td:first-child")?.textContent?.trim() ||
        "this patient";

      const confirmed = window.confirm(
        `Are you sure you want to delete ${name}? This cannot be undone.`,
      );
      if (confirmed) {
        form.submit();
      }
    });
  });

  // ───────────────────────────────────────────────
  // Appointment CRUD modal controls
  // ───────────────────────────────────────────────
  const apptModal = document.querySelector("#appointment-modal");
  const apptModalTitle = document.querySelector("#appointment-modal-title");
  const apptModalClose = document.querySelector("#appointment-modal-close");
  const apptModalCancel = document.querySelector("#appointment-modal-cancel");
  const openAddApptBtn = document.querySelector("#open-add-appointment");

  const apptFieldId = document.querySelector("#appointment-id");
  const apptFieldPatient = document.querySelector("#appointment-patient");
  const apptFieldDate = document.querySelector("#appointment-date");
  const apptFieldTime = document.querySelector("#appointment-time");
  const apptFieldStatus = document.querySelector("#appointment-status");

  const apptEditButtons = document.querySelectorAll(".btn-edit-appointment");
  const apptDeleteButtons = document.querySelectorAll(".btn-delete-appointment");
  const sidebarAddApptBtn = document.querySelector("#sidebar-add-appointment");
  const sidebarAddPatientBtn = document.querySelector("#sidebar-add-patient");

  const openApptModal = (mode, data) => {
    if (!apptModal) return;

    if (mode === "edit") {
      apptModalTitle.textContent = "Edit appointment";
      apptFieldId.value = data.id || "";
      apptFieldPatient.value = data.patientId || "";
      apptFieldDate.value = data.date || "";
      apptFieldTime.value = data.time || "";
      if (data.status) {
        apptFieldStatus.value = data.status;
      }
    } else {
      apptModalTitle.textContent = "Add appointment";
      apptFieldId.value = "";
      apptFieldPatient.value = "";
      apptFieldDate.value = "";
      apptFieldTime.value = "";
      apptFieldStatus.value = "Booked";
    }

    apptModal.classList.remove("modal--hidden");
  };

  const closeApptModal = () => {
    if (!apptModal) return;
    apptModal.classList.add("modal--hidden");
  };

  if (openAddApptBtn) {
    openAddApptBtn.addEventListener("click", () => openApptModal("add", {}));
  }

  if (apptModalClose) {
    apptModalClose.addEventListener("click", closeApptModal);
  }

  if (apptModalCancel) {
    apptModalCancel.addEventListener("click", (event) => {
      event.preventDefault();
      closeApptModal();
    });
  }

  if (apptModal) {
    const backdrop = apptModal.querySelector(".modal__backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", closeApptModal);
    }
  }

  apptEditButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest("tr");
      if (!row) return;

      const id = row.dataset.appointmentId || "";
      const patientId = row.dataset.patientId || "";
      const date = row.dataset.date || "";
      const time = row.dataset.time || "";
      const statusLabel = row.dataset.statusLabel || "Booked";

      openApptModal("edit", {
        id,
        patientId,
        date,
        time,
        status: statusLabel,
      });
    });
  });

  apptDeleteButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const form = btn.closest("form");
      const row = btn.closest("tr");
      if (!form || !row) return;

      const time = row.querySelector("td:nth-child(1)")?.textContent?.trim() || "";
      const patientName =
        row.querySelector("td:nth-child(2)")?.textContent?.trim() || "this patient";

      const confirmed = window.confirm(
        `Delete appointment at ${time} for ${patientName}? This cannot be undone.`,
      );
      if (confirmed) {
        form.submit();
      }
    });
  });

  // Sidebar quick actions
  if (sidebarAddApptBtn) {
    sidebarAddApptBtn.addEventListener("click", () => openApptModal("add", {}));
  }

  if (sidebarAddPatientBtn) {
    sidebarAddPatientBtn.addEventListener("click", () => openPatientModal("add", {}));
  }
});
