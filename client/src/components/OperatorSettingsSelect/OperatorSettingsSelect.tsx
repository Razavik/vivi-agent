import {
	useEffect,
	useLayoutEffect,
	useRef,
	useState,
	type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import {
	Bot,
	ChevronRight,
	Cpu,
	FileText,
	Globe,
	Monitor,
	Send,
	Settings2,
	Sparkles,
	Star,
	Trash2,
	X,
	type LucideIcon,
} from "lucide-react";
import styles from "./OperatorSettingsSelect.module.css";
import {
	CODEX_BASE_LABELS,
	CODEX_CONTEXT_LABEL,
	CODEX_EFFORT_LABELS,
	CODEX_EFFORT_ORDER,
	formatCodexLabel,
	formatOpenCodeLabel,
	isOpenCodeFreeModel,
	parseCodexModel,
	type ModelOption,
} from "../../utils/modelLabel";

interface SubAgentOption {
	name: string;
	displayName: string;
}

interface OperatorSettingsSelectProps {
	selectedModel: string;
	modelOptions: ModelOption[];
	onModelChange: (value: string) => void;
	pcControlMode: boolean;
	onPcControlModeChange: (enabled: boolean) => void;
	subAgentOptions: SubAgentOption[];
	preferredAgents: string[];
	onTogglePreferredAgent: (name: string) => void;
	onClearHistory?: () => void;
	onClearLogs?: () => void;
	onCompressMemory?: () => Promise<{
		compressed: boolean;
		before_count?: number;
		after_count?: number;
		reason?: string;
		error?: string;
	}>;
}

const AGENT_ICONS: Record<string, LucideIcon> = {
	file: FileText,
	system: Cpu,
	web: Globe,
	telegram: Send,
};

function iconFor(name: string): LucideIcon {
	return AGENT_ICONS[name] || Bot;
}

type TabKey = "model" | "mode" | "priority" | "memory" | null;

export function OperatorSettingsSelect({
	selectedModel,
	modelOptions,
	onModelChange,
	pcControlMode,
	onPcControlModeChange,
	subAgentOptions,
	preferredAgents,
	onTogglePreferredAgent,
	onClearHistory,
	onClearLogs,
	onCompressMemory,
}: OperatorSettingsSelectProps) {
	const [isOpen, setIsOpen] = useState(false);
	const [activeTab, setActiveTab] = useState<TabKey>(null);
	const [compressing, setCompressing] = useState(false);
	const [compressStatus, setCompressStatus] = useState<string | null>(null);
	const containerRef = useRef<HTMLDivElement>(null);
	const dropdownRef = useRef<HTMLDivElement>(null);
	const panelRef = useRef<HTMLDivElement>(null);
	const [panelPos, setPanelPos] = useState<{
		top: number;
		left: number;
	} | null>(null);

	// Инфо-поповер Codex-модели (контекст + уровень мышления) — отдельное
	// плавающее окошко справа от строки модели, а не разворачивание внутри
	// самого списка. Показывается при наведении на строку; без наведения —
	// для текущей выбранной модели по умолчанию.
	const [hoveredCodexBase, setHoveredCodexBase] = useState<string | null>(
		null,
	);
	const codexRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
	const codexPopoverRef = useRef<HTMLDivElement>(null);
	// Между строкой и поповером есть зазор (4px + сам поповер немного смещён
	// по вертикали) — мгновенный setHoveredCodexBase(null) на mouseleave
	// терял ховер при обычном диагональном движении мыши от строки к
	// поповеру. Задержка + отмена по повторному входу — стандартное решение
	// для hover-флаутов (как в подменю большинства UI-библиотек).
	const codexCloseTimeoutRef = useRef<number | null>(null);
	const cancelCodexClose = () => {
		if (codexCloseTimeoutRef.current !== null) {
			window.clearTimeout(codexCloseTimeoutRef.current);
			codexCloseTimeoutRef.current = null;
		}
	};
	const scheduleCodexClose = () => {
		cancelCodexClose();
		codexCloseTimeoutRef.current = window.setTimeout(() => {
			setHoveredCodexBase(null);
		}, 250);
	};
	useEffect(() => cancelCodexClose, []);
	const [codexPopoverPos, setCodexPopoverPos] = useState<{
		top: number;
		left: number;
	} | null>(null);

	const PANEL_MARGIN = 8;

	// Естественная позиция — якорем к dropdownRef, без предположений о
	// высоте панели (разные вкладки разной длины: "Режим" — одна строка,
	// "Модели" с Codex-моделями — намного длиннее). Клампить здесь по
	// гипотетическому максимуму (например всегда под max-height CSS)
	// неверно: короткие вкладки тогда без нужды улетают далеко от якоря.
	const naturalPanelPos = () => {
		if (!dropdownRef.current) return null;
		const rect = dropdownRef.current.getBoundingClientRect();
		return { top: rect.top, left: rect.right + 4 };
	};

	useLayoutEffect(() => {
		if (!isOpen || !dropdownRef.current) return;
		setPanelPos(naturalPanelPos());
		// activeTab влияет на высоту панели (разные вкладки — разная длина
		// списка), поэтому пересчитываем позицию и при смене вкладки, а не
		// только при открытии дропдауна.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isOpen, activeTab]);

	// Второй проход: после того как панель реально отрендерилась (и мы
	// знаем её фактические размеры), подвигаем её ровно настолько, чтобы
	// не вылезала за края viewport — вместо того чтобы заранее закладываться
	// на worst-case высоту, которая для коротких вкладок двигала панель
	// значительно дальше от якоря, чем нужно (см. правку выше).
	useLayoutEffect(() => {
		if (!isOpen || !panelPos || !panelRef.current) return;
		const panelRect = panelRef.current.getBoundingClientRect();
		let top = panelPos.top;
		let left = panelPos.left;
		const overflowBottom = panelRect.bottom - (window.innerHeight - PANEL_MARGIN);
		if (overflowBottom > 0) top = Math.max(PANEL_MARGIN, top - overflowBottom);
		const overflowRight = panelRect.right - (window.innerWidth - PANEL_MARGIN);
		if (overflowRight > 0) left = Math.max(PANEL_MARGIN, left - overflowRight);
		if (top !== panelPos.top || left !== panelPos.left) {
			setPanelPos({ top, left });
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isOpen, panelPos]);

	useEffect(() => {
		if (!isOpen) {
			setActiveTab(null);
			setCompressStatus(null);
			return;
		}
		const updatePos = () => setPanelPos(naturalPanelPos());
		window.addEventListener("scroll", updatePos, true);
		window.addEventListener("resize", updatePos);
		return () => {
			window.removeEventListener("scroll", updatePos, true);
			window.removeEventListener("resize", updatePos);
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isOpen]);

	useEffect(() => {
		// panelRef/codexPopoverRef смонтированы только пока их портал реально
		// отрендерен (панель — когда выбрана вкладка, поповер — только при
		// наведении на Codex-модель) — то есть в норме null. Раньше это стояло
		// в одной && -цепочке вместе с обязательным "текущий null → не закрывать",
		// поэтому пока поповер не наведён (почти всегда), всё выражение было
		// false и клик "снаружи" вообще никогда не срабатывал. Правильно —
		// закрывать, если клика не было ВНУТРИ ни одного из существующих
		// сейчас элементов.
		const isInside = (
			ref: React.RefObject<HTMLDivElement | null>,
			target: Node,
		) => ref.current !== null && ref.current.contains(target);
		const handleClickOutside = (e: MouseEvent) => {
			const target = e.target as Node;
			if (
				!isInside(containerRef, target) &&
				!isInside(dropdownRef, target) &&
				!isInside(panelRef, target) &&
				!isInside(codexPopoverRef, target)
			) {
				setIsOpen(false);
			}
		};
		if (isOpen) {
			document.addEventListener("mousedown", handleClickOutside);
		}
		return () =>
			document.removeEventListener("mousedown", handleClickOutside);
	}, [isOpen]);

	useEffect(() => {
		if (!isOpen || activeTab !== "model") setHoveredCodexBase(null);
	}, [isOpen, activeTab]);

	const selectedCodexModel = parseCodexModel(selectedModel);
	const selectedModelLabel = selectedCodexModel
		? formatCodexLabel(selectedCodexModel.base, selectedCodexModel.effort)
		: isOpenCodeFreeModel(selectedModel)
			? formatOpenCodeLabel(selectedModel)
			: modelOptions.find((opt) => opt.value === selectedModel)?.label ||
				selectedModel ||
				"Выбрать модель";

	// Codex-модели группируем по базе (gpt-5.4-mini, gpt-5.6-terra, ...) —
	// каждая база рендерится одной строкой, а не по одной строке на
	// каждый уровень reasoning-effort. Бесплатные модели OpenCode — в
	// отдельный список, без reasoning-effort и без поповера.
	const plainModelOptions: ModelOption[] = [];
	const openCodeOptions: ModelOption[] = [];
	const codexBaseEfforts = new Map<string, string[]>();
	for (const opt of modelOptions) {
		if (isOpenCodeFreeModel(opt.value)) {
			openCodeOptions.push(opt);
			continue;
		}
		const parsed = parseCodexModel(opt.value);
		if (!parsed) {
			plainModelOptions.push(opt);
			continue;
		}
		const efforts = codexBaseEfforts.get(parsed.base) ?? [];
		if (!efforts.includes(parsed.effort)) efforts.push(parsed.effort);
		codexBaseEfforts.set(parsed.base, efforts);
	}
	const codexBaseOrder = Object.keys(CODEX_BASE_LABELS);
	const codexBases = [...codexBaseEfforts.keys()].sort(
		(a, b) => codexBaseOrder.indexOf(a) - codexBaseOrder.indexOf(b),
	);

	// Поповер только по наведению — без ховера не показываем даже для уже
	// выбранной модели (раньше был fallback на selectedCodexModel, из-за
	// которого поповер всплывал сам по себе сразу при открытии вкладки).
	const popoverBase = activeTab === "model" ? hoveredCodexBase : null;

	useLayoutEffect(() => {
		if (!isOpen || !popoverBase) {
			setCodexPopoverPos(null);
			return;
		}
		const rowEl = codexRowRefs.current[popoverBase];
		if (!rowEl) return;
		const rect = rowEl.getBoundingClientRect();
		setCodexPopoverPos({ top: rect.top, left: rect.right + 4 });
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isOpen, popoverBase, panelPos]);

	// Тот же принцип, что и для основной панели (см. выше): сначала
	// естественная позиция у строки-якоря, затем — правка ровно на величину
	// реального переполнения после рендера, без worst-case допущений.
	useLayoutEffect(() => {
		if (!isOpen || !codexPopoverPos || !codexPopoverRef.current) return;
		const rect = codexPopoverRef.current.getBoundingClientRect();
		let top = codexPopoverPos.top;
		let left = codexPopoverPos.left;
		const overflowBottom = rect.bottom - (window.innerHeight - PANEL_MARGIN);
		if (overflowBottom > 0) top = Math.max(PANEL_MARGIN, top - overflowBottom);
		const overflowRight = rect.right - (window.innerWidth - PANEL_MARGIN);
		if (overflowRight > 0) left = Math.max(PANEL_MARGIN, left - overflowRight);
		if (top !== codexPopoverPos.top || left !== codexPopoverPos.left) {
			setCodexPopoverPos({ top, left });
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isOpen, codexPopoverPos]);

	const selectedAgentOptions = subAgentOptions.filter((opt) =>
		preferredAgents.includes(opt.name),
	);

	const handleCompressMemory = async () => {
		if (!onCompressMemory || compressing) return;
		setCompressing(true);
		setCompressStatus(null);
		try {
			const result = await onCompressMemory();
			if (result.compressed) {
				setCompressStatus(
					`Сжато: ${result.before_count} → ${result.after_count} сообщений`,
				);
			} else {
				setCompressStatus(
					result.error || result.reason || "Не удалось сжать",
				);
			}
		} catch {
			setCompressStatus("Не удалось сжать — проверь соединение");
		} finally {
			setCompressing(false);
		}
	};

	return (
		<div className={styles.wrap}>
			<div
				ref={containerRef}
				className={`${styles.container} ${isOpen ? styles.open : ""}`}
			>
				<button
					type="button"
					className={styles.trigger}
					onClick={() => setIsOpen((v) => !v)}
					title={`Настройки оператора: ${selectedModelLabel}${pcControlMode ? ", режим ПК" : ""}`}
				>
					<Settings2 size={14} className={styles.triggerIcon} />
					{pcControlMode && (
						<span className={styles.triggerDots}>
							<span
								className={styles.triggerDot}
								title="Режим ПК"
							>
								<Monitor size={8} />
							</span>
						</span>
					)}
					<svg
						className={styles.arrow}
						width="12"
						height="12"
						viewBox="0 0 14 14"
						fill="none"
					>
						<path
							d="M3 5L7 9L11 5"
							stroke="currentColor"
							strokeWidth="1.5"
							strokeLinecap="round"
							strokeLinejoin="round"
						/>
					</svg>
				</button>

				{isOpen && (
					<div ref={dropdownRef} className={styles.dropdown}>
						<div className={styles.tabsColumn}>
							<div
								className={`${styles.tabItem} ${activeTab === "model" ? styles.tabItemActive : ""}`}
								onMouseEnter={() => setActiveTab("model")}
								onClick={() => setActiveTab("model")}
							>
								<Cpu size={14} className={styles.tabIcon} />
								<span className={styles.tabLabel}>Модели</span>
								<ChevronRight
									size={14}
									className={styles.tabArrow}
								/>
							</div>
							<div
								className={`${styles.tabItem} ${activeTab === "mode" ? styles.tabItemActive : ""}`}
								onMouseEnter={() => setActiveTab("mode")}
								onClick={() => setActiveTab("mode")}
							>
								<Monitor size={14} className={styles.tabIcon} />
								<span className={styles.tabLabel}>Режим</span>
								<ChevronRight
									size={14}
									className={styles.tabArrow}
								/>
							</div>
							{subAgentOptions.length > 0 && (
								<div
									className={`${styles.tabItem} ${activeTab === "priority" ? styles.tabItemActive : ""}`}
									onMouseEnter={() =>
										setActiveTab("priority")
									}
									onClick={() => setActiveTab("priority")}
								>
									<Star
										size={14}
										className={styles.tabIcon}
									/>
									<span className={styles.tabLabel}>
										Приоритеты
									</span>
									{preferredAgents.length > 0 && (
										<span className={styles.tabBadge}>
											{preferredAgents.length}
										</span>
									)}
									<ChevronRight
										size={14}
										className={styles.tabArrow}
									/>
								</div>
							)}
							<div
								className={`${styles.tabItem} ${activeTab === "memory" ? styles.tabItemActive : ""}`}
								onMouseEnter={() => setActiveTab("memory")}
								onClick={() => setActiveTab("memory")}
							>
								<Trash2 size={14} className={styles.tabIcon} />
								<span className={styles.tabLabel}>Память</span>
								<ChevronRight
									size={14}
									className={styles.tabArrow}
								/>
							</div>
						</div>
					</div>
				)}
				{isOpen &&
					activeTab &&
					panelPos &&
					createPortal(
						<div
							ref={panelRef}
							className={styles.tabPanel}
							style={{
								top: panelPos.top,
								left: panelPos.left,
							}}
						>
							{activeTab === "model" && (
								<>
									{plainModelOptions.length > 0 && (
										<>
											<div className={styles.sectionLabel}>
												Ollama
											</div>
											{plainModelOptions.map((opt) => {
												const isSelected =
													opt.value === selectedModel;
												return (
													<div
														key={opt.value}
														className={`${styles.option} ${isSelected ? styles.selected : ""}`}
														onClick={() =>
															onModelChange(
																opt.value,
															)
														}
													>
														<span
															className={
																styles.optionLabel
															}
														>
															{opt.label}
														</span>
														{isSelected && <Check />}
													</div>
												);
											})}
										</>
									)}
									{codexBases.length > 0 && (
										<>
											<div className={styles.sectionLabel}>
												OpenAI
											</div>
											{codexBases.map((base) => {
												const isActive =
													selectedCodexModel?.base ===
													base;
												return (
													<div
														key={base}
														ref={(el) => {
															codexRowRefs.current[
																base
															] = el;
														}}
														className={`${styles.option} ${isActive ? styles.selected : ""}`}
														onMouseEnter={() => {
															cancelCodexClose();
															setHoveredCodexBase(
																base,
															);
														}}
														onMouseLeave={
															scheduleCodexClose
														}
														onClick={() => {
															const efforts = (
																codexBaseEfforts.get(
																	base,
																) ?? []
															);
															const defaultEffort =
																efforts.find(
																	(e) =>
																		e ===
																		"medium",
																) ??
																efforts[0];
															onModelChange(
																`codex:${base}[${isActive ? selectedCodexModel!.effort : defaultEffort}]`,
															);
														}}
													>
														<Sparkles
															size={14}
															className={
																styles.optionIcon
															}
														/>
														<span
															className={
																styles.optionLabel
															}
														>
															{CODEX_BASE_LABELS[
																base
															] ?? base}
														</span>
														{isActive && <Check />}
													</div>
												);
											})}
										</>
									)}
									{openCodeOptions.length > 0 && (
										<>
											<div className={styles.sectionLabel}>
												OpenCode
											</div>
											{openCodeOptions.map((opt) => {
												const isSelected =
													opt.value === selectedModel;
												return (
													<div
														key={opt.value}
														className={`${styles.option} ${isSelected ? styles.selected : ""}`}
														onClick={() =>
															onModelChange(
																opt.value,
															)
														}
													>
														<Sparkles
															size={14}
															className={
																styles.optionIcon
															}
														/>
														<span
															className={
																styles.optionLabel
															}
														>
															{formatOpenCodeLabel(
																opt.value,
															)}
														</span>
														{isSelected && <Check />}
													</div>
												);
											})}
										</>
									)}
								</>
							)}

							{activeTab === "mode" && (
								<>
									<div className={styles.sectionLabel}>
										Режим
									</div>
									<div
										className={`${styles.option} ${styles.toggleOption}`}
										onClick={() =>
											onPcControlModeChange(
												!pcControlMode,
											)
										}
									>
										<Monitor
											size={14}
											className={styles.optionIcon}
										/>
										<span className={styles.optionLabel}>
											Управление ПК
										</span>
										<span
											className={`${styles.miniSwitch} ${pcControlMode ? styles.miniSwitchOn : ""}`}
										>
											<span
												className={
													styles.miniSwitchThumb
												}
											/>
										</span>
									</div>
								</>
							)}

							{activeTab === "priority" &&
								subAgentOptions.length > 0 && (
									<>
										<div className={styles.sectionLabel}>
											Приоритет саб-агентов
											{pcControlMode && (
												<span
													className={
														styles.sectionHint
													}
												>
													{" "}
													— выключит режим ПК
												</span>
											)}
										</div>
										{subAgentOptions.map((agent) => {
											const Icon = iconFor(agent.name);
											const isSelected =
												preferredAgents.includes(
													agent.name,
												);
											return (
												<div
													key={agent.name}
													className={`${styles.option} ${isSelected ? styles.selected : ""}`}
													onClick={() =>
														onTogglePreferredAgent(
															agent.name,
														)
													}
												>
													<Icon
														size={14}
														className={
															styles.optionIcon
														}
													/>
													<span
														className={
															styles.optionLabel
														}
													>
														{agent.displayName}
													</span>
													{isSelected && <Check />}
												</div>
											);
										})}
									</>
								)}

							{activeTab === "memory" && (
								<>
									<div className={styles.sectionLabel}>
										Память
									</div>
									<div
										className={`${styles.option} ${styles.dangerOption}`}
										onClick={() => {
											onClearHistory?.();
											onClearLogs?.();
											setIsOpen(false);
										}}
									>
										<Trash2
											size={14}
											className={styles.optionIcon}
										/>
										<span className={styles.optionLabel}>
											Очистить память
										</span>
									</div>
									{onCompressMemory && (
										<div
											className={`${styles.option} ${compressing ? styles.optionDisabled : ""}`}
											onClick={handleCompressMemory}
											title="Заменит старую часть истории на краткую сводку от модели, не трогая последние сообщения"
										>
											<Sparkles
												size={14}
												className={styles.optionIcon}
											/>
											<span
												className={styles.optionLabel}
											>
												{compressing
													? "Сжимаю…"
													: "Сжать контекст"}
											</span>
										</div>
									)}
									{compressStatus && (
										<div className={styles.sectionHint2}>
											{compressStatus}
										</div>
									)}
								</>
							)}
						</div>,
						document.body,
					)}
				{isOpen &&
					popoverBase &&
					codexPopoverPos &&
					createPortal(
						<div
							ref={codexPopoverRef}
							className={styles.codexPopover}
							style={{
								top: codexPopoverPos.top,
								left: codexPopoverPos.left,
							}}
							onMouseEnter={cancelCodexClose}
							onMouseLeave={scheduleCodexClose}
						>
							{(() => {
								const efforts = (
									codexBaseEfforts.get(popoverBase) ?? []
								).sort(
									(a, b) =>
										CODEX_EFFORT_ORDER.indexOf(a) -
										CODEX_EFFORT_ORDER.indexOf(b),
								);
								const isSelectedBase =
									selectedCodexModel?.base === popoverBase;
								const defaultEffort =
									efforts.find((e) => e === "medium") ??
									efforts[0];
								const currentEffort = isSelectedBase
									? selectedCodexModel!.effort
									: defaultEffort;
								const currentIndex = Math.max(
									0,
									efforts.indexOf(currentEffort),
								);
								const percent =
									efforts.length > 1
										? (currentIndex /
												(efforts.length - 1)) *
											100
										: 100;
								return (
									<>
										<div
											className={
												styles.codexPopoverTitle
											}
										>
											{CODEX_BASE_LABELS[popoverBase] ??
												popoverBase}
										</div>
										<div
											className={
												styles.codexPopoverContext
											}
										>
											{CODEX_CONTEXT_LABEL}
										</div>
										<div
											className={
												styles.codexPopoverDivider
											}
										/>
										<div
											className={
												styles.codexPopoverEffortHeader
											}
										>
											<span
												className={
													styles.codexPopoverEffortLabel
												}
											>
												Уровень мышления
											</span>
											<span
												className={
													styles.effortCurrentLabel
												}
											>
												{CODEX_EFFORT_LABELS[
													currentEffort
												] ?? currentEffort}
											</span>
										</div>
										<input
											type="range"
											className={styles.effortSlider}
											min={0}
											max={
												Math.max(
													efforts.length - 1,
													0,
												)
											}
											step={1}
											value={currentIndex}
											style={
												{
													"--fill": `${percent}%`,
												} as CSSProperties
											}
											onClick={(e) =>
												e.stopPropagation()
											}
											onChange={(e) => {
												const effort =
													efforts[
														Number(
															e.target.value,
														)
													];
												if (effort) {
													onModelChange(
														`codex:${popoverBase}[${effort}]`,
													);
												}
											}}
										/>
										<div
											className={
												styles.effortSliderTicks
											}
										>
											{efforts.map((effort) => (
												<span key={effort}>
													{CODEX_EFFORT_LABELS[
														effort
													]?.slice(0, 3) ?? effort}
												</span>
											))}
										</div>
									</>
								);
							})()}
						</div>,
						document.body,
					)}
			</div>

			{(selectedModel ||
				pcControlMode ||
				selectedAgentOptions.length > 0) && (
				<div className={styles.chips}>
					{selectedModel && (
						<span
							className={styles.chip}
							title={selectedModelLabel}
						>
							<Cpu size={12} />
							{selectedModelLabel}
						</span>
					)}
					{pcControlMode && (
						<span className={styles.chip}>
							<Monitor size={12} />
							ПК
							<button
								type="button"
								className={styles.chipRemove}
								onClick={() => onPcControlModeChange(false)}
								title="Выключить режим ПК"
							>
								<X size={11} />
							</button>
						</span>
					)}
					{selectedAgentOptions.map((opt) => {
						const Icon = iconFor(opt.name);
						return (
							<span
								key={opt.name}
								className={styles.chip}
								title={opt.displayName}
							>
								<Icon size={12} />
								<button
									type="button"
									className={styles.chipRemove}
									onClick={() =>
										onTogglePreferredAgent(opt.name)
									}
									title="Убрать из приоритета"
								>
									<X size={11} />
								</button>
							</span>
						);
					})}
				</div>
			)}
		</div>
	);
}

function Check() {
	return (
		<svg
			className={styles.check}
			width="13"
			height="13"
			viewBox="0 0 13 13"
			fill="none"
		>
			<path
				d="M2 6.5L5.5 10L11 3"
				stroke="currentColor"
				strokeWidth="1.6"
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}
