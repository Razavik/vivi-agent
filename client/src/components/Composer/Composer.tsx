import { useRef } from "react";
import { ImagePlus, SendHorizontal, Square, X } from "lucide-react";
import styles from "./Composer.module.css";
import { LiveStatus } from "../LiveStatus/LiveStatus";
import { OperatorSettingsSelect } from "../OperatorSettingsSelect/OperatorSettingsSelect";
import { formatModelLabel } from "../../utils/modelLabel";

interface ModelOption {
	value: string;
	label: string;
}

interface SubAgentOption {
	name: string;
	displayName: string;
}

interface ComposerProps {
	task: string;
	images: string[];
	contextTokens: number;
	contextLimit: number;
	modelSupportsVision: boolean;
	selectedModel: string;
	modelOptions: ModelOption[];
	onModelChange: (value: string) => void;
	onTaskChange: (value: string) => void;
	onImagesChange: (images: string[]) => void;
	onRun: () => void;
	onStop: () => void;
	isRunning: boolean;
	liveStatus: string;
	pcControlMode: boolean;
	onPcControlModeChange: (enabled: boolean) => void;
	subAgentOptions?: SubAgentOption[];
	preferredAgents?: string[];
	onTogglePreferredAgent?: (name: string) => void;
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

export function Composer({
	task,
	images,
	contextTokens,
	contextLimit,
	modelSupportsVision,
	selectedModel,
	modelOptions,
	onModelChange,
	onTaskChange,
	onImagesChange,
	onRun,
	onStop,
	isRunning,
	liveStatus,
	pcControlMode,
	onPcControlModeChange,
	subAgentOptions = [],
	preferredAgents = [],
	onTogglePreferredAgent,
	onClearHistory,
	onClearLogs,
	onCompressMemory,
}: ComposerProps) {
	const fileInputRef = useRef<HTMLInputElement>(null);
	const blockedByVision = images.length > 0 && !modelSupportsVision;
	const tokenPercent = Math.max(
		0,
		Math.min(
			100,
			Math.round((contextTokens / Math.max(contextLimit, 1)) * 100),
		),
	);
	const readFilesAsBase64 = (files: File[]): Promise<string[]> => {
		const imageFiles = files.filter((f) => f.type.startsWith("image/"));
		return Promise.all(
			imageFiles.map(
				(file) =>
					new Promise<string>((resolve) => {
						const reader = new FileReader();
						reader.onload = () =>
							resolve((reader.result as string).split(",")[1]);
						reader.readAsDataURL(file);
					}),
			),
		);
	};

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = Array.from(e.target.files || []);
		e.target.value = "";
		if (!files.length) return;
		readFilesAsBase64(files).then((b64s) => {
			if (b64s.length > 0) onImagesChange([...images, ...b64s]);
		});
	};

	const removeImage = (idx: number) => {
		onImagesChange(images.filter((_, i) => i !== idx));
	};

	const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
		const items = Array.from(e.clipboardData.items);
		const imageItems = items.filter((item) =>
			item.type.startsWith("image/"),
		);
		if (imageItems.length === 0) return;
		e.preventDefault();
		const readers = imageItems.map(
			(item) =>
				new Promise<string>((resolve) => {
					const file = item.getAsFile();
					if (!file) return resolve("");
					const reader = new FileReader();
					reader.onload = () => {
						const result = reader.result as string;
						resolve(result.split(",")[1]);
					};
					reader.readAsDataURL(file);
				}),
		);
		Promise.all(readers).then((b64s) => {
			onImagesChange([...images, ...b64s.filter(Boolean)]);
		});
	};

	return (
		<div className={styles.composer}>
			{isRunning && <LiveStatus status={liveStatus} />}
			<div className={styles.composerRow}>
				{images.length > 0 && (
					<div className={styles.imagePreviewRow}>
						{images.map((b64, idx) => (
							<div key={idx} className={styles.imagePreviewItem}>
								<img
									src={`data:image/png;base64,${b64}`}
									className={styles.imagePreviewThumb}
									alt={`attachment-${idx}`}
								/>
								<button
									className={styles.imageRemoveBtn}
									onClick={() => removeImage(idx)}
									title="Удалить"
								>
									<X size={12} />
								</button>
							</div>
						))}
					</div>
				)}
				{blockedByVision && (
					<div className={styles.visionWarning}>
						Модель «{formatModelLabel(selectedModel, modelOptions)}»
						не умеет анализировать изображения
					</div>
				)}
				<div className={styles.inputRow}>
					<input
						ref={fileInputRef}
						type="file"
						accept="image/*"
						multiple
						style={{ display: "none" }}
						onChange={handleFileChange}
					/>
					<div className={styles.textareaWrapper}>
						<textarea
							value={task}
							onChange={(e) => onTaskChange(e.target.value)}
							placeholder="Введите запрос..."
							onKeyDown={(e) => {
								if (
									e.key === "Enter" &&
									!e.shiftKey &&
									!isRunning &&
									!blockedByVision
								) {
									e.preventDefault();
									onRun();
								}
							}}
							onPaste={handlePaste}
						/>
					</div>
					<div className={styles.buttonsWrapper}>
						<div className={styles.controlStrip}>
							<div className={styles.actionGroup}>
								<OperatorSettingsSelect
									selectedModel={selectedModel}
									modelOptions={modelOptions}
									onModelChange={onModelChange}
									pcControlMode={pcControlMode}
									onPcControlModeChange={
										onPcControlModeChange
									}
									subAgentOptions={subAgentOptions}
									preferredAgents={preferredAgents}
									onTogglePreferredAgent={(name) =>
										onTogglePreferredAgent?.(name)
									}
									onClearHistory={onClearHistory}
									onClearLogs={onClearLogs}
									onCompressMemory={onCompressMemory}
								/>
							</div>
						</div>
						<div className={styles.rightControls}>
							<button
								className={styles.attachCircleBtn}
								onClick={() => fileInputRef.current?.click()}
								title="Прикрепить изображение"
								disabled={isRunning}
							>
								<ImagePlus size={20} />
							</button>
							<div className={styles.contextOrbGroup}>
								<button
									type="button"
									className={styles.contextOrb}
									style={{
										["--context-fill" as string]: `${tokenPercent}%`,
									}}
									aria-label={`Контекстное окно ${tokenPercent} процентов`}
									title="Контекстное окно"
								>
									<span className={styles.contextOrbInner}>
										<span
											className={styles.contextOrbValue}
										></span>
									</span>
								</button>
								<div
									className={styles.contextTooltip}
									role="status"
									aria-live="polite"
								>
									<div className={styles.contextTooltipTitle}>
										Контекстное окно
									</div>
									<div
										className={styles.contextTooltipPercent}
									>
										{tokenPercent}% заполнено
									</div>
									<div className={styles.contextTooltipScale}>
										<div
											className={
												styles.contextTooltipScaleFill
											}
											style={{
												width: `${tokenPercent}%`,
											}}
										/>
									</div>
									<div
										className={styles.contextTooltipTokens}
									>
										{contextTokens > 0 &&
											`Использовано ${contextTokens.toLocaleString()} токенов`}
									</div>
								</div>
							</div>
							<button
								className={styles.sendBtn}
								onClick={isRunning ? onStop : onRun}
								disabled={!isRunning && blockedByVision}
								title={
									blockedByVision
										? "Модель не поддерживает изображения"
										: undefined
								}
							>
								{isRunning ? (
									<Square size={16} fill="currentColor" />
								) : (
									<SendHorizontal size={16} />
								)}
							</button>
						</div>
					</div>
				</div>
			</div>
			<div className={styles.hint}>
				Agent 1 может допускать ошибки. Проверяй важную информацию.
			</div>
		</div>
	);
}
