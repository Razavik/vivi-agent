import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Search, Store, Trash2 } from "lucide-react";
import { fetchJson } from "../../utils/http";
import styles from "./SkillsPage.module.css";

interface OperatorSkill {
	id: string;
	title: string;
	description?: string;
	source: "core" | "custom" | "market" | string;
	enabled: boolean;
	installed: boolean;
	requires: string[];
	tags: string[];
	body: string;
	path?: string;
}

interface SkillsResponse {
	skills: OperatorSkill[];
	market: OperatorSkill[];
	limits?: { max_chars?: number };
	error?: string;
}

const EMPTY_RESPONSE: SkillsResponse = { skills: [], market: [] };
type SkillsTab = "installed" | "market" | "create";

function splitCsv(value: string) {
	return value
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
}

export function SkillsPage() {
	const queryClient = useQueryClient();
	const [search, setSearch] = useState("");
	const [title, setTitle] = useState("");
	const [requires, setRequires] = useState("");
	const [body, setBody] = useState("");
	const [tags, setTags] = useState("custom");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [activeTab, setActiveTab] = useState<SkillsTab>("installed");

	const { data, isLoading } = useQuery({
		queryKey: ["operator-skills"],
		queryFn: () => fetchJson<SkillsResponse>("/api/operator-skills", EMPTY_RESPONSE),
	});

	const invalidate = () => {
		void queryClient.invalidateQueries({ queryKey: ["operator-skills"] });
	};

	const createSkill = useMutation({
		mutationFn: () =>
			fetchJson<SkillsResponse>("/api/operator-skills", EMPTY_RESPONSE, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					title,
					body,
					requires: splitCsv(requires),
					tags: splitCsv(tags),
				}),
			}),
		onSuccess: () => {
			setTitle("");
			setBody("");
			setRequires("");
			setTags("custom");
			invalidate();
		},
	});

	const toggleSkill = useMutation({
		mutationFn: (payload: { id: string; enabled: boolean }) =>
			fetchJson<SkillsResponse>("/api/operator-skills/enabled", EMPTY_RESPONSE, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload),
			}),
		onSuccess: invalidate,
	});

	const installSkill = useMutation({
		mutationFn: (id: string) =>
			fetchJson<SkillsResponse>("/api/operator-skills/install", EMPTY_RESPONSE, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ id }),
			}),
		onSuccess: invalidate,
	});

	const deleteSkill = useMutation({
		mutationFn: (id: string) =>
			fetchJson<SkillsResponse>(`/api/operator-skills/${id}/delete`, EMPTY_RESPONSE, {
				method: "POST",
			}),
		onSuccess: invalidate,
	});

	const skills = data?.skills ?? [];
	const market = data?.market ?? [];
	const selected = skills.find((skill) => skill.id === selectedId) ?? skills[0];
	const query = search.trim().toLowerCase();
	const filteredSkills = useMemo(
		() =>
			skills.filter((skill) => {
				if (!query) return true;
				return [skill.title, skill.description, skill.id, skill.tags.join(" ")]
					.join(" ")
					.toLowerCase()
					.includes(query);
			}),
		[query, skills],
	);
	const filteredMarket = useMemo(
		() =>
			market.filter((skill) => {
				if (!query) return true;
				return [skill.title, skill.description, skill.id, skill.tags.join(" ")]
					.join(" ")
					.toLowerCase()
					.includes(query);
			}),
		[market, query],
	);

	return (
		<div className={styles.page}>
			<header className={styles.header}>
				<div>
					<div className={styles.eyebrow}>Operator Skills</div>
					<h1 className={styles.title}>Скиллы Оператора</h1>
					<p className={styles.subtitle}>
						Управляй поведенческими навыками Оператора: включай базовые, добавляй свои и
						устанавливай заготовки из локального маркета.
					</p>
				</div>
				<div className={styles.headerActions}>
					<div className={styles.stat}>
						<strong>{skills.filter((skill) => skill.enabled).length}</strong>
						<span>активно</span>
					</div>
					<div className={styles.stat}>
						<strong>{market.length}</strong>
						<span>в маркете</span>
					</div>
				</div>
			</header>

			<div className={styles.toolbar}>
				<div className={styles.tabs} role="tablist" aria-label="Разделы скиллов">
					<button
						type="button"
						className={activeTab === "installed" ? styles.tabActive : styles.tab}
						onClick={() => setActiveTab("installed")}
					>
						<BookOpen size={15} />
						Установленные
					</button>
					<button
						type="button"
						className={activeTab === "market" ? styles.tabActive : styles.tab}
						onClick={() => setActiveTab("market")}
					>
						<Store size={15} />
						Маркет
					</button>
					<button
						type="button"
						className={activeTab === "create" ? styles.tabActive : styles.tab}
						onClick={() => setActiveTab("create")}
					>
						<Plus size={15} />
						Свой навык
					</button>
				</div>
				<div className={styles.searchBox}>
					<Search size={16} />
					<input
						value={search}
						onChange={(event) => setSearch(event.target.value)}
						placeholder="Поиск по навыкам"
					/>
				</div>
			</div>

			{activeTab === "installed" && (
				<div className={styles.twoColumn}>
					<section className={styles.panel}>
						<div className={styles.panelHeader}>
							<BookOpen size={16} />
							<span>Установленные</span>
							<strong>{skills.length}</strong>
						</div>
						{isLoading ? (
							<div className={styles.empty}>Загрузка...</div>
						) : filteredSkills.length === 0 ? (
							<div className={styles.empty}>Навыки не найдены</div>
						) : (
							<div className={styles.skillList}>
								{filteredSkills.map((skill) => (
									<button
										type="button"
										key={skill.id}
										className={`${styles.skillItem} ${selected?.id === skill.id ? styles.active : ""}`}
										onClick={() => setSelectedId(skill.id)}
									>
										<div className={styles.skillTop}>
											<span>{skill.title}</span>
											<span className={styles.source}>{skill.source}</span>
										</div>
										<div className={styles.skillMeta}>
											{skill.enabled ? "Включён" : "Выключен"}
											{skill.requires.length > 0 ? ` · tools: ${skill.requires.length}` : ""}
										</div>
									</button>
								))}
							</div>
						)}
					</section>

					<section className={styles.panel}>
					<div className={styles.panelHeader}>
						<span>Детали</span>
					</div>
					{selected ? (
						<div className={styles.details}>
							<div className={styles.detailsTop}>
								<div>
									<h2>{selected.title}</h2>
									<p>{selected.description || "Без описания"}</p>
								</div>
								<label className={styles.switch}>
									<input
										type="checkbox"
										checked={selected.enabled}
										onChange={(event) =>
											toggleSkill.mutate({
												id: selected.id,
												enabled: event.target.checked,
											})
										}
									/>
									<span />
								</label>
							</div>
							<div className={styles.tags}>
								{selected.tags.map((tag) => (
									<span key={tag}>{tag}</span>
								))}
								{selected.requires.map((tool) => (
									<span key={tool}>{tool}</span>
								))}
							</div>
							<pre className={styles.preview}>{selected.body}</pre>
							{selected.source === "custom" && (
								<button
									type="button"
									className={styles.dangerButton}
									onClick={() => deleteSkill.mutate(selected.id)}
								>
									<Trash2 size={15} />
									Удалить
								</button>
							)}
						</div>
					) : (
						<div className={styles.empty}>Выбери навык</div>
					)}
					</section>
				</div>
			)}

			{activeTab === "create" && (
				<section className={styles.panel}>
					<div className={styles.panelHeader}>
						<Plus size={16} />
						<span>Свой навык</span>
					</div>
					<div className={styles.form}>
						<input
							value={title}
							onChange={(event) => setTitle(event.target.value)}
							placeholder="Название навыка"
							className={styles.input}
						/>
						<input
							value={requires}
							onChange={(event) => setRequires(event.target.value)}
							placeholder="requires: system_key_press, take_screenshot"
							className={styles.input}
						/>
						<input
							value={tags}
							onChange={(event) => setTags(event.target.value)}
							placeholder="tags: ui, browser"
							className={styles.input}
						/>
						<textarea
							value={body}
							onChange={(event) => setBody(event.target.value)}
							placeholder="Опиши процедуру: цель, шаги, проверку результата..."
							className={styles.textarea}
						/>
						<button
							type="button"
							className={styles.primaryButton}
							disabled={!title.trim() || !body.trim() || createSkill.isPending}
							onClick={() => createSkill.mutate()}
						>
							Добавить навык
						</button>
					</div>
				</section>
			)}

			{activeTab === "market" && (
				<section className={styles.marketPanel}>
					<div className={styles.panelHeader}>
						<Store size={16} />
						<span>Маркет заготовок</span>
						<strong>{market.length}</strong>
					</div>
					<div className={styles.marketGrid}>
						{filteredMarket.map((skill) => (
							<div key={skill.id} className={styles.marketItem}>
								<div className={styles.marketTitle}>{skill.title}</div>
								<div className={styles.marketText}>
									{skill.description || "Готовый операторский сценарий"}
								</div>
								<div className={styles.tags}>
									{skill.tags.map((tag) => (
										<span key={tag}>{tag}</span>
									))}
								</div>
								<button
									type="button"
									className={styles.ghostButton}
									disabled={skill.installed || installSkill.isPending}
									onClick={() => installSkill.mutate(skill.id)}
								>
									{skill.installed ? "Установлено" : "Установить"}
								</button>
							</div>
						))}
					</div>
				</section>
			)}
		</div>
	);
}
