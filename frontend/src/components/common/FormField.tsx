import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement>;
type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

interface BaseFieldProps {
  error?: string;
  helperText?: string;
  label: string;
}

interface FormFieldInputProps extends BaseFieldProps {
  inputProps: InputProps;
  kind?: "input";
}

interface FormFieldSelectProps extends BaseFieldProps {
  children: ReactNode;
  kind: "select";
  selectProps: SelectProps;
}

type FormFieldProps = FormFieldInputProps | FormFieldSelectProps;

export function FormField(props: FormFieldProps) {
  return (
    <label className="form-field">
      <span>{props.label}</span>
      {props.kind === "select" ? (
        <select {...props.selectProps}>{props.children}</select>
      ) : (
        <input {...props.inputProps} />
      )}
      {props.helperText ? <small>{props.helperText}</small> : null}
      {props.error ? <em>{props.error}</em> : null}
    </label>
  );
}
