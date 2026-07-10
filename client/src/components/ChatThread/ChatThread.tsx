import { useEffect, useRef, useState } from "react";
import {
	Bot,
	Braces,
	FolderSearch,
	Sparkles,
	TerminalSquare,
} from "lucide-react";
import styles from "./ChatThread.module.css";
import { MessageRow } from "../MessageRow/MessageRow";
import { ThoughtBlockInThread } from "../ThoughtBlockInThread/ThoughtBlockInThread";
import { ToolBlock } from "../ToolBlock/ToolBlock";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatEvent } from "../../types";
import { isWindowsPath, openPath } from "../../utils/openPath";
import { normalizeAssistantText } from "../../utils/renderText";

interface ChatThreadProps {
	events: ChatEvent[];
	currentAnswer: string;
	liveThought?: string;
}

const STARTER_CARDS = [
	{
		icon: FolderSearch,
		title: "Разобрать проект",
		text: "Проверить архитектуру, риски и места для улучшения.",
	},
	{
		icon: TerminalSquare,
		title: "Проверить запуск",
		text: "Посмотреть backend, frontend и логи.",
	},
	{
		icon: Braces,
		title: "Внести правки",
		text: "Описать задачу, а агент подберёт нужные шаги.",
	},
];

export function ChatThread({
	events,
	currentAnswer,
	liveThought,
}: ChatThreadProps) {
	const threadRef = useRef<HTMLDivElement>(null);
	const [isAtBottom, setIsAtBottom] = useState(true);
	const [visibleCount, setVisibleCount] = useState(50);
	const LOAD_MORE_INCREMENT = 50;

	// Сбрасываем visibleCount при новых сообщениях
	const loadMore = () => {
		setVisibleCount((prev) => prev + LOAD_MORE_INCREMENT);
	};

	const markdownComponents: Components = {
		pre({ children }) {
			return <pre className={styles.codeBlock}>{children}</pre>;
		},
		code({ children, ...props }) {
			const text =
				typeof children === "string"
					? children
					: String(children ?? "");
			if (isWindowsPath(text)) {
				return (
					<code
						className={`${styles.inlineCode} ${styles.pathLink}`}
						title="Открыть в проводнике"
						onClick={() => void openPath(text.trim())}
						{...props}
					>
						{text}
					</code>
				);
			}
			return (
				<code className={styles.inlineCode} {...props}>
					{children}
				</code>
			);
		},
	};

	// Проверяем находится ли пользователь в самом низу
	const checkIfAtBottom = () => {
		if (!threadRef.current) return;
		const { scrollTop, scrollHeight, clientHeight } = threadRef.current;
		const threshold = 50; // Порог в пикселях
		setIsAtBottom(scrollHeight - scrollTop - clientHeight < threshold);
	};

	// Автоскролл к новым сообщениям только если пользователь в самом низу
	useEffect(() => {
		if (threadRef.current && isAtBottom) {
			threadRef.current.scrollTop = threadRef.current.scrollHeight;
		}
	}, [events, currentAnswer, isAtBottom]);

	// Отслеживаем скролл пользователя
	useEffect(() => {
		const current = threadRef.current;
		if (!current) return;

		current.addEventListener("scroll", checkIfAtBottom);
		return () => current.removeEventListener("scroll", checkIfAtBottom);
	}, []);

	// Группируем события по ответам ассистента
	const groupedEvents: Array<{
		type: "user" | "assistant";
		events: ChatEvent[];
	}> = [];
	let currentGroup: ChatEvent[] = [];

	for (const event of events) {
		if (event.type === "message" && event.role === "user") {
			// Сохраняем предыдущую группу ассистента
			if (currentGroup.length > 0) {
				groupedEvents.push({ type: "assistant", events: currentGroup });
				currentGroup = [];
			}
			// Сообщение пользователя - отдельная группа
			groupedEvents.push({ type: "user", events: [event] });
		} else {
			// События ассистента (thought, tool_result, message)
			currentGroup.push(event);
		}
	}

	// Добавляем последнюю группу ассистента
	if (currentGroup.length > 0) {
		groupedEvents.push({ type: "assistant", events: currentGroup });
	}

	// Ограничиваем количество отображаемых событий
	const hasMoreMessages = groupedEvents.length > visibleCount;
	const visibleEvents = hasMoreMessages
		? groupedEvents.slice(-visibleCount)
		: groupedEvents;
	const isEmpty =
		groupedEvents.length === 0 && !currentAnswer && !liveThought;

	return (
		<div ref={threadRef} className={styles.chatThread}>
			{isEmpty && (
				<div className={styles.emptyState}>
					<div className={styles.emptyGlow} />
					<div className={styles.emptyMark}>
						<Bot size={30} />
					</div>
					<div className={styles.emptyEyebrow}>
						<Sparkles size={14} />
						<span>Agent 1 готов к задаче</span>
					</div>
					<h1 className={styles.emptyTitle}>
						Что сегодня доведём до рабочего состояния?
					</h1>
					<p className={styles.emptyText}>
						Опиши цель обычными словами. Можно попросить проверить
						проект, найти баг, доработать клиент или аккуратно
						пройтись по агентной системе.
					</p>
					<div className={styles.emptyCards}>
						{STARTER_CARDS.map((card) => {
							const Icon = card.icon;
							return (
								<div
									key={card.title}
									className={styles.emptyCard}
								>
									<div className={styles.emptyCardIcon}>
										<Icon size={18} />
									</div>
									<div>
										<div className={styles.emptyCardTitle}>
											{card.title}
										</div>
										<div className={styles.emptyCardText}>
											{card.text}
										</div>
									</div>
								</div>
							);
						})}
					</div>
				</div>
			)}
			{hasMoreMessages && (
				<button className={styles.loadMoreBtn} onClick={loadMore}>
					Загрузить старые сообщения (
					{groupedEvents.length - visibleCount})
				</button>
			)}
			{visibleEvents.map((group, groupIdx) => {
				if (group.type === "user") {
					return (
						<MessageRow
							key={`user-${groupIdx}`}
							message={group.events[0]}
						/>
					);
				}

				// Контейнер для событий ассистента
				return (
					<div
						key={`assistant-${groupIdx}`}
						className={styles.assistantGroup}
					>
						{group.events.map((event, idx) => {
							switch (event.type) {
								case "message":
									return (
										<div
											key={idx}
											className={`${styles.eventRow} ${styles.answerBlock}`}
										>
											<div
												className={styles.eventContent}
											>
												<ReactMarkdown
													remarkPlugins={[remarkGfm]}
													components={
														markdownComponents
													}
												>
													{normalizeAssistantText(
														event.content || "",
													)}
												</ReactMarkdown>
											</div>
										</div>
									);
								case "thought":
									return (
										<ThoughtBlockInThread
											key={idx}
											thought={event.thought!}
											id={`thought-${groupIdx}-${idx}`}
										/>
									);
								case "tool_result":
								case "tool_use":
									return (
										<ToolBlock
											key={idx}
											action={event.action!}
											result={event.result}
										/>
									);
								default:
									return null;
							}
						})}
					</div>
				);
			})}
			{liveThought && (
				<div className={styles.assistantGroup}>
					<ThoughtBlockInThread
						thought={liveThought}
						id="live-thought"
						streaming
					/>
				</div>
			)}
			{currentAnswer && (
				<div className={`${styles.assistantGroup}`}>
					<div className={`${styles.eventRow} ${styles.answerBlock}`}>
						<div className={styles.eventContent}>
							<ReactMarkdown
								remarkPlugins={[remarkGfm]}
								components={markdownComponents}
							>
								{normalizeAssistantText(currentAnswer)}
							</ReactMarkdown>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
