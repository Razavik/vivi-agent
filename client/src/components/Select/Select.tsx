import { useState, useRef, useEffect } from "react";
import styles from "./Select.module.css";

interface SelectOption {
	value: string;
	label: string;
	dot?: string;
}

interface SelectProps {
	value: string;
	onChange: (value: string) => void;
	options: SelectOption[];
	placeholder?: string;
	className?: string;
}

export function Select({ value, onChange, options, placeholder, className }: SelectProps) {
	const [isOpen, setIsOpen] = useState(false);
	const [highlightedIndex, setHighlightedIndex] = useState(-1);
	const containerRef = useRef<HTMLDivElement>(null);
	const listRef = useRef<HTMLDivElement>(null);

	const selectedOption = options.find((opt) => opt.value === value);

	const handleClick = () => {
		setIsOpen(!isOpen);
		setHighlightedIndex(-1);
	};

	const handleOptionClick = (optValue: string) => {
		onChange(optValue);
		setIsOpen(false);
		setHighlightedIndex(-1);
	};

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (!isOpen) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				setIsOpen(true);
			}
			return;
		}

		switch (e.key) {
			case "ArrowDown":
				e.preventDefault();
				setHighlightedIndex((prev) => {
					const next = prev + 1;
					return next < options.length ? next : prev;
				});
				break;
			case "ArrowUp":
				e.preventDefault();
				setHighlightedIndex((prev) => {
					const next = prev - 1;
					return next >= 0 ? next : prev;
				});
				break;
			case "Enter":
				e.preventDefault();
				if (highlightedIndex >= 0 && highlightedIndex < options.length) {
					handleOptionClick(options[highlightedIndex].value);
				}
				break;
			case "Escape":
				setIsOpen(false);
				setHighlightedIndex(-1);
				break;
		}
	};

	const scrollToHighlighted = () => {
		if (highlightedIndex >= 0 && listRef.current) {
			const highlightedElement = listRef.current.children[highlightedIndex] as HTMLElement;
			if (highlightedElement) {
				highlightedElement.scrollIntoView({ block: "nearest" });
			}
		}
	};

	useEffect(() => {
		scrollToHighlighted();
	}, [highlightedIndex]);

	useEffect(() => {
		const handleClickOutside = (e: MouseEvent) => {
			if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
				setIsOpen(false);
			}
		};

		if (isOpen) {
			document.addEventListener("mousedown", handleClickOutside);
		}

		return () => {
			document.removeEventListener("mousedown", handleClickOutside);
		};
	}, [isOpen]);

	return (
		<div
			ref={containerRef}
			className={`${styles.container} ${isOpen ? styles.open : ""} ${className || ""}`}
			onKeyDown={handleKeyDown}
			tabIndex={0}
		>
			<div className={styles.trigger} onClick={handleClick}>
				{selectedOption?.dot && (
					<span className={styles.dot} style={{ background: selectedOption.dot }} />
				)}
				<span className={styles.value}>
					{selectedOption ? selectedOption.label : placeholder || "Выберите..."}
				</span>
				<svg
					className={styles.arrow}
					width="14"
					height="14"
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
			</div>

			{isOpen && (
				<div className={styles.dropdown} ref={listRef}>
					{options.map((opt, index) => {
						const isSelected = opt.value === value;
						return (
							<div
								key={opt.value}
								className={`${styles.option} ${isSelected ? styles.selected : ""} ${
									index === highlightedIndex ? styles.highlighted : ""
								}`}
								onClick={() => handleOptionClick(opt.value)}
								onMouseEnter={() => setHighlightedIndex(index)}
							>
								{opt.dot && (
									<span
										className={styles.optionDot}
										style={{ background: opt.dot }}
									/>
								)}
								<span className={styles.optionLabel}>{opt.label}</span>
								{isSelected && (
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
								)}
							</div>
						);
					})}
				</div>
			)}
		</div>
	);
}
