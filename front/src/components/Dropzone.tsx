import { useState, type DragEvent } from "react";

interface Props {
  onFile: (file: File) => void;
}

export function Dropzone({ onFile }: Props) {
  const [dragging, setDragging] = useState(false);

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onFile(file);
  }

  return (
    <label
      className={`dropzone${dragging ? " is-dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input
        type="file"
        accept=".mp4,.mov,.mkv,.webm,.avi"
        className="visually-hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
      <span className="dropzone-title">Arrastra tu video aquí</span>
      <span className="dropzone-hint">o toca para elegirlo desde tu dispositivo</span>
      <span className="dropzone-formats">MP4, MOV, MKV, WEBM o AVI, hasta 500 MB</span>
    </label>
  );
}
