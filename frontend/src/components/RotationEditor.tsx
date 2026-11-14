import React from "react";
import type { CropSummary, Rotation, SlotIn, SowDate, MonthStr, FortnightDayStr } from "../types";

interface RotationEditorProps {
  rotation: Rotation;
  onChange: (rotation: Rotation) => void;
  crops: CropSummary[];
}

const MONTHS: { value: MonthStr; label: string }[] = [
  { value: "01", label: "01 - Enero" },
  { value: "02", label: "02 - Febrero" },
  { value: "03", label: "03 - Marzo" },
  { value: "04", label: "04 - Abril" },
  { value: "05", label: "05 - Mayo" },
  { value: "06", label: "06 - Junio" },
  { value: "07", label: "07 - Julio" },
  { value: "08", label: "08 - Agosto" },
  { value: "09", label: "09 - Septiembre" },
  { value: "10", label: "10 - Octubre" },
  { value: "11", label: "11 - Noviembre" },
  { value: "12", label: "12 - Diciembre" },
];

const FORTNIGHTS: { value: FortnightDayStr; label: string }[] = [
  { value: "01", label: "1ª quincena (día 01)" },
  { value: "16", label: "2ª quincena (día 16)" },
];

export const RotationEditor: React.FC<RotationEditorProps> = ({
  rotation,
  onChange,
  crops,
}) => {
  const handleAddYear = () => {
    if (rotation.years.length >= 3) return;
    const newYear = {
      slots: [{ crop_id: crops[0]?.id ?? "soya", sow_date: "11-16" as SowDate }],
    };
    onChange({
      ...rotation,
      years: [...rotation.years, newYear],
    });
  };

  const handleRemoveYear = (yearIndex: number) => {
    if (rotation.years.length <= 1) return;
    const updatedYears = rotation.years.filter((_, idx) => idx !== yearIndex);
    onChange({
      ...rotation,
      years: updatedYears,
    });
  };

  const handleAddSlot = (yearIndex: number) => {
    const year = rotation.years[yearIndex];
    if (!year || year.slots.length >= 2) return;
    const newSlot: SlotIn = {
      crop_id: crops[1]?.id ?? "maiz",
      sow_date: "05-01" as SowDate,
    };
    const updatedYears = [...rotation.years];
    updatedYears[yearIndex] = {
      ...year,
      slots: [...year.slots, newSlot],
    };
    onChange({ ...rotation, years: updatedYears });
  };

  const handleRemoveSlot = (yearIndex: number, slotIndex: number) => {
    const year = rotation.years[yearIndex];
    if (!year || year.slots.length <= 1) return;
    const updatedSlots = year.slots.filter((_, idx) => idx !== slotIndex);
    const updatedYears = [...rotation.years];
    updatedYears[yearIndex] = {
      ...year,
      slots: updatedSlots,
    };
    onChange({ ...rotation, years: updatedYears });
  };

  const handleSlotCropChange = (yearIndex: number, slotIndex: number, cropId: string) => {
    const updatedYears = [...rotation.years];
    const year = updatedYears[yearIndex];
    if (!year) return;
    const updatedSlots = [...year.slots];
    updatedSlots[slotIndex] = {
      ...updatedSlots[slotIndex],
      crop_id: cropId,
    };
    updatedYears[yearIndex] = { ...year, slots: updatedSlots };
    onChange({ ...rotation, years: updatedYears });
  };

  const handleSlotDateChange = (
    yearIndex: number,
    slotIndex: number,
    part: "month" | "day",
    val: string
  ) => {
    const updatedYears = [...rotation.years];
    const year = updatedYears[yearIndex];
    if (!year) return;
    const updatedSlots = [...year.slots];
    const currentSowDate = updatedSlots[slotIndex].sow_date;
    const [currMonth, currDay] = currentSowDate.split("-");
    const newMonth = part === "month" ? val : currMonth;
    const newDay = part === "day" ? val : currDay;
    const newSowDate = `${newMonth}-${newDay}` as SowDate;

    updatedSlots[slotIndex] = {
      ...updatedSlots[slotIndex],
      sow_date: newSowDate,
    };
    updatedYears[yearIndex] = { ...year, slots: updatedSlots };
    onChange({ ...rotation, years: updatedYears });
  };

  // Check if at least one crop is harvestable
  const hasHarvestable = rotation.years.some((y) =>
    y.slots.some((s) => {
      const c = crops.find((item) => item.id === s.crop_id);
      return c ? c.cosechable : true;
    })
  );

  return (
    <div className="rotation-editor card">
      <div className="editor-header">
        <div>
          <h3 className="section-title">Esquema de Rotación Actual ({rotation.years.length} {rotation.years.length === 1 ? "año" : "años"})</h3>
          <p className="section-subtitle">
            Configure de 1 a 3 años y de 1 a 2 cultivos por campaña agrícola.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={handleAddYear}
          disabled={rotation.years.length >= 3}
          title="Agregar un año adicional al ciclo de rotación"
        >
          + Agregar año
        </button>
      </div>

      {!hasHarvestable && (
        <div className="alert alert-warning" style={{ margin: "12px 0" }}>
          ⚠️ La rotación debe incluir al menos un cultivo de cosecha comercial (no solo coberturas).
        </div>
      )}

      <div className="years-list">
        {rotation.years.map((year, yIdx) => (
          <div key={`year-${yIdx}`} className="year-container">
            <div className="year-header">
              <span className="year-badge">Año {yIdx + 1}</span>
              <div className="year-actions">
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={() => handleAddSlot(yIdx)}
                  disabled={year.slots.length >= 2}
                  title="Agregar un segundo cultivo en este año"
                >
                  + Agregar cultivo
                </button>
                {rotation.years.length > 1 && (
                  <button
                    type="button"
                    className="btn btn-danger-outline btn-sm"
                    onClick={() => handleRemoveYear(yIdx)}
                    title="Eliminar este año del ciclo"
                  >
                    Eliminar año
                  </button>
                )}
              </div>
            </div>

            <div className="slots-grid">
              {year.slots.map((slot, sIdx) => {
                const [monthStr, dayStr] = slot.sow_date.split("-");
                const currentCrop = crops.find((c) => c.id === slot.crop_id);

                return (
                  <div key={`slot-${yIdx}-${sIdx}`} className="slot-card">
                    <div className="slot-header">
                      <span className="slot-label">
                        Cultivo {sIdx + 1} {currentCrop && !currentCrop.cosechable && "(Cobertura)"}
                      </span>
                      {year.slots.length > 1 && (
                        <button
                          type="button"
                          className="btn-text btn-danger"
                          onClick={() => handleRemoveSlot(yIdx, sIdx)}
                          title="Quitar este cultivo"
                        >
                          ✕ Quitar
                        </button>
                      )}
                    </div>

                    <div className="form-group">
                      <label className="form-label" htmlFor={`crop-select-${yIdx}-${sIdx}`}>
                        Cultivo:
                      </label>
                      <select
                        id={`crop-select-${yIdx}-${sIdx}`}
                        className="form-select"
                        value={slot.crop_id}
                        onChange={(e) => handleSlotCropChange(yIdx, sIdx, e.target.value)}
                      >
                        {crops.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.nombre} ({c.familia}) {!c.cosechable ? "[cobertura]" : ""} — parámetros pendientes de verificación: {c.n_verificar_pendientes}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="date-pickers-row">
                      <div className="form-group flex-1">
                        <label className="form-label" htmlFor={`month-select-${yIdx}-${sIdx}`}>
                          Mes de siembra:
                        </label>
                        <select
                          id={`month-select-${yIdx}-${sIdx}`}
                          className="form-select"
                          value={monthStr}
                          onChange={(e) =>
                            handleSlotDateChange(yIdx, sIdx, "month", e.target.value)
                          }
                        >
                          {MONTHS.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="form-group flex-1">
                        <label className="form-label" htmlFor={`fortnight-select-${yIdx}-${sIdx}`}>
                          Quincena:
                        </label>
                        <select
                          id={`fortnight-select-${yIdx}-${sIdx}`}
                          className="form-select"
                          value={dayStr}
                          onChange={(e) =>
                            handleSlotDateChange(yIdx, sIdx, "day", e.target.value)
                          }
                        >
                          {FORTNIGHTS.map((f) => (
                            <option key={f.value} value={f.value}>
                              {f.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
