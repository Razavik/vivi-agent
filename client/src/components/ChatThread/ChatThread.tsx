import { useEffect, useRef, useState } from "react";
import styles from "./ChatThread.module.css";
import { MessageRow } from "../MessageRow/MessageRow";
import { ThoughtBlockInThread } from "../ThoughtBlockInThread/ThoughtBlockInThread";
import { ToolBlock } from "../ToolBlock/ToolBlock";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatEvent, PlanItem } from "../../types";
import { isWindowsPath, openPath } from "../../utils/openPath";

interface ChatThreadProps {
	events: ChatEvent[];
	currentAnswer: string;
	liveThought?: string;
}

const PLAN_ICONS: Record<string, string> = {
	completed: "✓",
	in_progress: "◌",
	pending: "○",
};

function PlanBlock({ plan }: { plan: PlanItem[] }) {
	if (!plan.length) return null;
	const done = plan.filter((i) => i.status === "completed").length;
	return (
		<div className={styles.planBlock}>
			<div className={styles.planHeader}>
				<span className={styles.planLabel}>План</span>
				<span className={styles.planCounter}>
					{done} / {plan.length} tasks done
				</span>
			</div>
			<div className={styles.planList}>
				{plan.map((item) => (
					<div key={item.id} className={`${styles.planItem} ${styles[item.status]}`}>
						<span className={styles.planIcon}>{PLAN_ICONS[item.status] ?? "○"}</span>
						<span className={styles.planContent}>{item.content}</span>
					</div>
				))}
			</div>
		</div>
	);
}

export function ChatThread({ events, currentAnswer, liveThought }: ChatThreadProps) {
	const threadRef = useRef<HTMLDivElement>(null);
	const [isAtBottom, setIsAtBottom] = useState(true);
	const [visibleCount, setVisibleCount] = useState(50);
	const MAX_INITIAL_MESSAGES = 50;
	const LOAD_MORE_INCREMENT = 50;

	// Сбрасываем visibleCount при новых сообщениях
	useEffect(() => {
		setVisibleCount(MAX_INITIAL_MESSAGES);
	}, [events.length]);

	const loadMore = () => {
		setVisibleCount((prev) => prev + LOAD_MORE_INCREMENT);
	};

	const markdownComponents = {
		pre({ children }: any) {
			return <pre className={styles.codeBlock}>{children}</pre>;
		},
		code({ children, ...props }: any) {
			const text = typeof children === "string" ? children : String(children ?? "");
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
	const visibleEvents = hasMoreMessages ? groupedEvents.slice(-visibleCount) : groupedEvents;

	return (
		<div ref={threadRef} className={styles.chatThread}>
			{hasMoreMessages && (
				<button className={styles.loadMoreBtn} onClick={loadMore}>
					Загрузить старые сообщения ({groupedEvents.length - visibleCount})
				</button>
			)}
			{visibleEvents.map((group, groupIdx) => {
				if (group.type === "user") {
					return <MessageRow key={`user-${groupIdx}`} message={group.events[0]} />;
				}

				// Контейнер для событий ассистента
				return (
					<div key={`assistant-${groupIdx}`} className={styles.assistantGroup}>
						{group.events.map((event, idx) => {
							switch (event.type) {
								case "message":
									if (event.plan && event.plan.length > 0 && !event.content) {
										return <PlanBlock key={idx} plan={event.plan} />;
									}
									return (
										<div
											key={idx}
											className={`${styles.eventRow} ${styles.answerBlock}`}
										>
											<div className={styles.eventContent}>
												<ReactMarkdown
													remarkPlugins={[remarkGfm]}
													components={markdownComponents}
												>
													{event.content}
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
					<ThoughtBlockInThread thought={liveThought} id="live-thought" streaming />
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
								{currentAnswer}
							</ReactMarkdown>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
