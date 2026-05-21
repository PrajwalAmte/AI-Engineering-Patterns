interface Props {
  src: string
  alt: string
  caption?: string
}

export function Diagram({ src, alt, caption }: Props) {
  return (
    <figure className="my-8">
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden bg-white dark:bg-gray-900 p-4">
        <img
          src={src}
          alt={alt}
          className="w-full h-auto dark:[filter:invert(1)_hue-rotate(180deg)_saturate(0.8)]"
          loading="lazy"
        />
      </div>
      {caption && (
        <figcaption className="mt-2 text-center text-sm text-gray-500 dark:text-gray-400">
          {caption}
        </figcaption>
      )}
    </figure>
  )
}
