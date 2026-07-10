import { useState } from "react";
import styles from "./ImageThumbGrid.module.css";

interface ImageThumbGridProps {
	images: string[];
}

/** Сетка маленьких превью (data-URI или обычные URL) с раскрытием в lightbox по клику. */
export function ImageThumbGrid({ images }: ImageThumbGridProps) {
	const [lightbox, setLightbox] = useState<string | null>(null);

	if (!images.length) return null;

	return (
		<>
			<div className={styles.grid}>
				{images.map((src, idx) => (
					<img
						key={`${idx}-${src}`}
						src={src}
						className={styles.thumb}
						alt={`image-${idx}`}
						onClick={() => setLightbox(src)}
					/>
				))}
			</div>
			{lightbox && (
				<div className={styles.overlay} onClick={() => setLightbox(null)}>
					<img
						src={lightbox}
						className={styles.full}
						alt="full"
						onClick={(e) => e.stopPropagation()}
					/>
					<button
						className={styles.close}
						onClick={() => setLightbox(null)}
					>
						×
					</button>
				</div>
			)}
		</>
	);
}
